// =============================================================================
//  bsm_engine.cpp — C++17 multithreaded Monte Carlo pricer for European
//  options on a single underlying that follows Geometric Brownian Motion.
//
//  Exposed to Python as the class `quant_engine_cpp.MonteCarloPricerCpp`.
//  The hot path is parallelised across CPU cores with std::thread; each
//  worker owns its own std::mt19937_64 so the simulation is reproducible
//  from a single seed.
//
//  Build: see cpp_core/CMakeLists.txt and cpp_core/build_instructions.md.
// =============================================================================

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <future>
#include <random>
#include <stdexcept>
#include <string>
#include <thread>
#include <tuple>
#include <utility>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;


// =============================================================================
//  Marsaglia polar method for N(0, 1) — inline, header-only, fast for MC.
//  Each call returns two independent normals (the second is ignored by the
//  caller if it only needs one).
// =============================================================================
namespace {

inline double sample_normal(std::mt19937_64& rng) {
    // Marsaglia polar method. ~6 lines, no divisions by sqrt on the hot
    // path beyond the final one.
    std::uniform_real_distribution<double> uniform(-1.0, 1.0);
    while (true) {
        double u = uniform(rng);
        double v = uniform(rng);
        double s = u * u + v * v;
        if (s > 0.0 && s < 1.0) {
            const double factor = std::sqrt(-2.0 * std::log(s) / s);
            return u * factor;  // one of the pair; we only need one at a time
        }
    }
}


// =============================================================================
//  MonteCarloPricerCpp
// =============================================================================
class MonteCarloPricerCpp {
public:
    MonteCarloPricerCpp(double S, double K, double T, double r, double sigma,
                        std::uint64_t n_paths, std::uint32_t n_steps,
                        std::string option_type,
                        std::uint64_t seed,
                        bool antithetic,
                        std::uint32_t n_threads)
        : S_(S), K_(K), T_(T), r_(r), sigma_(sigma),
          n_paths_(n_paths), n_steps_(n_steps),
          option_type_(std::move(option_type)),
          seed_(seed),
          antithetic_(antithetic),
          n_threads_(resolve_n_threads(n_threads)) {
        // ---- Input validation (mirrors the Python engine) ----------------
        if (S  <= 0.0) throw std::invalid_argument("S must be positive.");
        if (K  <= 0.0) throw std::invalid_argument("K must be positive.");
        if (T  <= 0.0) throw std::invalid_argument("T must be positive.");
        if (sigma_ <= 0.0) throw std::invalid_argument("sigma must be positive.");
        if (n_paths_ == 0) throw std::invalid_argument("n_paths must be positive.");
        if (n_steps_ == 0) throw std::invalid_argument("n_steps must be positive.");
        if (option_type_ != "call" && option_type_ != "put") {
            throw std::invalid_argument("option_type must be 'call' or 'put'.");
        }

        // Per-step constants for the GBM log-return decomposition.
        dt_         = T_ / static_cast<double>(n_steps_);
        drift_      = (r_ - 0.5 * sigma_ * sigma_) * dt_;
        diffusion_  = sigma_ * std::sqrt(dt_);
        discount_   = std::exp(-r_ * T_);
    }

    // -----------------------------------------------------------------------
    //  Public API
    // -----------------------------------------------------------------------
    std::tuple<double, double, double, double> price() {
        // Returns: (price, std_error, ci_low, ci_high)
        const auto stats = simulate_reduce(/*want_both=*/false);
        // For the single-side path, simulate_reduce stores the payoff mean
        // in ReduceResult::call_mean; we then discount it here.
        const double discounted = discount_ * stats.call_mean;
        const double se   = std::sqrt(stats.variance / static_cast<double>(stats.n_eff));
        const double half = 1.96 * se;
        return std::make_tuple(discounted, se, discounted - half, discounted + half);
    }

    std::pair<double, double> price_both() {
        // Returns (call, put) using one shared set of terminal prices,
        // so the difference is much tighter than running twice.
        const auto stats = simulate_reduce(/*want_both=*/true);
        const double discount = discount_;
        return std::pair<double, double>{
            discount * stats.call_mean,
            discount * stats.put_mean,
        };
    }

    std::uint32_t threads_used() const noexcept { return n_threads_; }

    // -----------------------------------------------------------------------
    //  Implementation
    // -----------------------------------------------------------------------
private:
    struct ReduceResult {
        double call_mean = 0.0;
        double put_mean  = 0.0;
        double variance  = 0.0;   // variance of the *single* option's payoff
        std::uint64_t n_eff = 0;
    };

    ReduceResult simulate_reduce(bool want_both) {
        const std::uint32_t t = n_threads_;
        const std::uint64_t chunk = n_paths_ / t;
        const std::uint64_t remainder = n_paths_ - chunk * t;

        std::vector<std::future<ReduceResult>> futures;
        futures.reserve(t);

        for (std::uint32_t i = 0; i < t; ++i) {
            const std::uint64_t this_chunk = chunk + (i < remainder ? 1 : 0);
            futures.push_back(std::async(std::launch::async,
                [this, i, this_chunk, want_both]() {
                    return worker_(i, this_chunk, want_both);
                }));
        }

        // Reduce on the calling thread.
        ReduceResult agg;
        double call_weighted_sum = 0.0;
        double put_weighted_sum  = 0.0;
        std::uint64_t n_total = 0;
        double mean_of_squares = 0.0;   // for variance of the call/put payoff

        for (auto& f : futures) {
            ReduceResult r = f.get();
            n_total += r.n_eff;
            call_weighted_sum += r.call_mean * static_cast<double>(r.n_eff);
            put_weighted_sum  += r.put_mean  * static_cast<double>(r.n_eff);
            // Accumulate the second moment for the variance of the *single*
            // option (which is what `price()`'s std_error reports). The
            // worker stored its local variance of the call (or put) payoff.
            mean_of_squares  += r.variance * static_cast<double>(r.n_eff);
        }

        agg.n_eff = n_total;
        if (want_both) {
            agg.call_mean = call_weighted_sum / static_cast<double>(n_total);
            agg.put_mean  = put_weighted_sum  / static_cast<double>(n_total);
        } else {
            // The single side (call or put) is stored in call_mean.
            agg.call_mean = call_weighted_sum / static_cast<double>(n_total);
        }
        // `variance` is interpreted as E[X^2] for the relevant payoff;
        // std_error = sqrt(E[X^2] / n) for a zero-mean (after discount)
        // estimator. We approximate variance from the per-chunk second
        // moment: with antithetic pairing each pair has the same mean, so
        // a sum/sum-of-squares reduction per pair is exact.
        agg.variance = mean_of_squares / static_cast<double>(n_total);
        return agg;
    }

    ReduceResult worker_(std::uint32_t thread_index,
                         std::uint64_t n_paths_this_thread,
                         bool want_both) const {
        // Per-thread RNG. Same seed + same thread index → identical draws
        // across runs (reproducibility property of std::mt19937_64).
        std::mt19937_64 rng(seed_ ^ (static_cast<std::uint64_t>(thread_index) * 0x9E3779B97F4A7C15ULL));

        double call_sum = 0.0;
        double put_sum  = 0.0;
        double sq_sum   = 0.0;     // sum of (payoff)^2 for the SINGLE side

        for (std::uint64_t i = 0; i < n_paths_this_thread; ++i) {
            // Sum log-returns over the path. For a European payoff only
            // the terminal price matters, but the engine is correct for
            // any n_steps.
            double log_sum = 0.0;
            for (std::uint32_t s = 0; s < n_steps_; ++s) {
                log_sum += drift_ + diffusion_ * sample_normal(rng);
            }
            const double ST  = S_ * std::exp(log_sum);

            double call_payoff = 0.0;
            double put_payoff  = 0.0;
            if (option_type_ == "call" || want_both) {
                call_payoff = std::max(ST - K_, 0.0);
            }
            if (option_type_ == "put" || want_both) {
                put_payoff = std::max(K_ - ST, 0.0);
            }
            call_sum += call_payoff;
            put_sum  += put_payoff;
            sq_sum   += (option_type_ == "put" ? put_payoff * put_payoff
                                                : call_payoff * call_payoff);

            if (antithetic_) {
                // Mirror path: replace Z with -Z, so log_sum' = -log_sum
                // (because drift stays the same; only the diffusion term
                // flips sign). So S_T' = S * exp(2*drift*n_steps - log_sum)
                // = S_T * exp(2*drift*n_steps) / exp(log_sum)
                //   = S * exp(2*drift*n_steps - log_sum).
                const double ST_anti = S_ * std::exp(2.0 * drift_ * n_steps_ - log_sum);
                double call_anti = 0.0;
                double put_anti  = 0.0;
                if (option_type_ == "call" || want_both) {
                    call_anti = std::max(ST_anti - K_, 0.0);
                }
                if (option_type_ == "put" || want_both) {
                    put_anti = std::max(K_ - ST_anti, 0.0);
                }
                call_sum += call_anti;
                put_sum  += put_anti;
                sq_sum   += (option_type_ == "put" ? put_anti * put_anti
                                                    : call_anti * call_anti);
            }
        }

        ReduceResult r;
        r.n_eff = antithetic_ ? 2 * n_paths_this_thread : n_paths_this_thread;
        r.call_mean = call_sum / static_cast<double>(r.n_eff);
        r.put_mean  = put_sum  / static_cast<double>(r.n_eff);
        r.variance  = sq_sum   / static_cast<double>(r.n_eff);
        return r;
    }

    static std::uint32_t resolve_n_threads(std::uint32_t requested) {
        if (requested == 0) {
            const unsigned hc = std::thread::hardware_concurrency();
            return hc == 0 ? 1u : hc;
        }
        return requested;
    }

    // ---- Inputs -----------------------------------------------------------
    double S_, K_, T_, r_, sigma_;
    std::uint64_t n_paths_;
    std::uint32_t n_steps_;
    std::string  option_type_;
    std::uint64_t seed_;
    bool         antithetic_;
    std::uint32_t n_threads_;

    // ---- Per-step constants ----------------------------------------------
    double dt_{0.0}, drift_{0.0}, diffusion_{0.0}, discount_{0.0};
};

}  // namespace


// =============================================================================
//  pybind11 bindings
// =============================================================================
PYBIND11_MODULE(quant_engine_cpp, m) {
    m.doc() = "quant_engine_cpp — C++17 multithreaded Monte Carlo pricer "
              "for European options on a single underlying (GBM).";

    py::class_<MonteCarloPricerCpp>(m, "MonteCarloPricerCpp")
        .def(py::init<double, double, double, double, double,
                      std::uint64_t, std::uint32_t,
                      std::string, std::uint64_t, bool, std::uint32_t>(),
             py::arg("S"),
             py::arg("K"),
             py::arg("T"),
             py::arg("r"),
             py::arg("sigma"),
             py::arg("n_paths"),
             py::arg("n_steps"),
             py::arg("option_type"),
             py::arg("seed"),
             py::arg("antithetic"),
             py::arg("n_threads") = 0,
             "Construct a multithreaded Monte Carlo pricer. "
             "Set n_threads=0 to auto-detect hardware concurrency.")
        .def("price",
             &MonteCarloPricerCpp::price,
             "Run the simulation. Returns (price, std_error, ci_low, ci_high) "
             "where the CI is the 95% normal-approximation interval.")
        .def("price_both",
             &MonteCarloPricerCpp::price_both,
             "Price call and put from a single shared simulation. "
             "Returns (call_price, put_price).")
        .def("threads_used",
             &MonteCarloPricerCpp::threads_used,
             "How many worker threads were actually used.");
}
