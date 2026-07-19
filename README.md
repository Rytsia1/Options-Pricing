# Options Pricing Engine

A Python-based quantitative finance repository designed to model, analyze, and calculate financial option prices. This project provides analytical and numerical methods to value derivatives, making it a reliable tool for financial modeling and quantitative analysis.

## 🚀 Features

* **Black-Scholes Model (`src/black_scholes.py`)**: Implements the standard analytical formula for pricing European-style options.
* **Monte Carlo Simulation (`src/monte_carlo.py`)**: Provides a numerical method for options pricing, capable of handling complex or path-dependent derivatives.
* **Market Data Management (`src/market_data.py`)**: Dedicated modules to process and manage the market data variables required for accurate calculations.
* **Robust Testing (`tests/`)**: Fully covered by unit tests using the `pytest` framework to ensure mathematical accuracy and code reliability.

## 📂 Project Structure

* `main.py`: The main entry point for the application.
* `src/`: Contains the core mathematical models and data processing scripts.
* `tests/`: Contains isolated unit tests for all core functionalities (`test_bsm.py`, `test_market_data.py`, `test_monte_carlo.py`).
* `requirements.txt`: Lists all the necessary Python dependencies to run the project.

## 🛠️ Technologies Used

* **Language**: Python, C++
* **Testing Framework**: pytest (v9.1.1)
