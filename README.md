# Options Pricing Engine

A Python-based quantitative finance repository designed to model, analyze, and calculate financial option prices[cite: 1]. This project provides analytical and numerical methods to value derivatives, making it a reliable tool for financial modeling and quantitative analysis.

## 🚀 Features

* **Black-Scholes Model (`src/black_scholes.py`)**: Implements the standard analytical formula for pricing European-style options[cite: 1].
* **Monte Carlo Simulation (`src/monte_carlo.py`)**: Provides a numerical method for options pricing, capable of handling complex or path-dependent derivatives[cite: 1].
* **Market Data Management (`src/market_data.py`)**: Dedicated modules to process and manage the market data variables required for accurate calculations[cite: 1].
* **Robust Testing (`tests/`)**: Fully covered by unit tests using the `pytest` framework to ensure mathematical accuracy and code reliability[cite: 1].

## 📂 Project Structure

* `main.py`: The main entry point for the application[cite: 1].
* `src/`: Contains the core mathematical models and data processing scripts[cite: 1].
* `tests/`: Contains isolated unit tests for all core functionalities (`test_bsm.py`, `test_market_data.py`, `test_monte_carlo.py`)[cite: 1].
* `requirements.txt`: Lists all the necessary Python dependencies to run the project[cite: 1].

## 🛠️ Technologies Used

* **Language**: Python[cite: 1]
* **Testing Framework**: pytest (v9.1.1)[cite: 1]
