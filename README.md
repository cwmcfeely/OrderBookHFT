[![Build Status](https://github.com/cwmcfeely/OrderBookHFT/actions/workflows/ci.yml/badge.svg)](https://github.com/cwmcfeely/OrderBookHFT/actions)
[![Python Version](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)

# OrderBookHFT

OrderBookHFT is a high-frequency trading (HFT) simulation environment focused on FIX protocol, order book modeling, 
strategy development, visualisation and a modern DevOps pipeline. Built with a modular architecture and Jupyter Notebook
support, this repository allows anyone to gain more knowledge on how to develop, test, and analyse trading strategies 
against European Equities with delayed and/or synthetic order book data.

## 🚀 Features
- **FIX Protocol Engine**: Simulates exchange connectivity using FIX 4.4.
- **Order Book Simulation**: Tools for modeling and simulating order book dynamics.
- **Strategy Development**: Modular framework for implementing, testing, and comparing trading strategies. 
- **Real-Time Analytics Dashboard**: Flask + Plotly dashboard for live monitoring of order flow, trades, P&L and latency
- **Configurable**: Easily load more symbols via `config.yaml`.
- **Risk Controls**: Position limits, stop-loss and ability to halt trading.
- **Jupyter Notebook Support**: Example notebooks for exploration and visualisation.
- **DevOps Pipeline**: Automated linting, testing, security scanning and multi-environment deployment (Actions + Azure).
- **Dockerised Environment**: Run the application in a Docker container for consistency and reproducibility.

## 📂 Project Structure
```
OrderBookHFT/
├── api/                # REST API and dashboard (Flask)
├── app/                # Core application (order book, matching engine, FIX, etc.)
├── data/               # Symbol lists and market data
├── logs/               # Dedicated logging for each strategy
├── Notebooks/          # Jupyter notebooks for data analysis.
├── strategies/         # Trading strategies (market making, momentum, etc.)
├── tests/              # Unit, integration, and system tests
├── config.yaml         # Central configuration for symbols
├── requirements.txt    # Python dependencies
├── Dockerfile          # Docker build file
└── README.md           # ReadMe documentation
```

## 🛠️ Built With / Tech Stack
- **Python 3.12** – Core language for backend, strategies, and simulation 
- **Flask** – REST API and real-time analytics dashboard 
- **Plotly** – Interactive data visualization in the dashboard 
- **Pandas & NumPy** – Data analysis and order book modeling
- **Jupyter Notebook** – Research, analysis, and prototyping 
- **Node.js & ESLint** – Frontend linting and static analysis 
- **Docker** – Containerisation for consistent, portable deployments
- **GitHub Actions** – CI/CD pipeline for automated linting, testing, security, build, and deployment
- **Azure App Service** – Cloud hosting for pilot, staging, and production environments
- **Trivy** – Container vulnerability scanning
- **Bandit, pip-audit, CodeQL** – Python security scanning

**Project Management**: [OrderBookHFT Project Board](https://github.com/cwmcfeely/OrderBookHFT/projects)

## 🔒 DevOps & Security

- **Automated CI/CD Pipeline:**  
  - Linting (Python, JS), testing (unit, integration, system), security scanning (Bandit, pip-audit, CodeQL, Trivy), Docker build/push, and Azure deployment.
  - DORA metrics logging for deployment frequency and reliability.
- **Secret Scanning:**  
  - GitHub secret scanning enabled to catch accidental leaks.
- **Branch Protection:**  
  - Required PR reviews and branch protection on all main environments.
- **Environment-Specific Configuration:**  
  - Secure use of environment variables and secrets for each deployment stage.

## Getting Started
### Prerequisites

#### To Run with Docker (Recommended)
- **Docker**: Install Docker Desktop or Docker Engine (https://docs.docker.com/get-docker/)
- **Git** (optional, for cloning the repository): https://git-scm.com/

#### To Run Locally (without Docker)
- **Python 3.12**
- **pip** (Python package installer)
- **Jupyter Notebook** (install via pip or Anaconda)
- **Node.js & npm** 
- **API key** from https://eodhd.com/ (add to config.yaml)
- **Note:** Local installation requires you to manually install the dependencies listed in `requirements.txt` and (if applicable) `package.json`.

### Installation

#### With Docker
```bash
docker build -t orderbookhft .
docker run -p 8000:8000 orderbookhft
```

#### Local (Manual)
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
Update API_KEY = ("EOD_API_KEY") with registered API_KEY
python3 -m api.server
```

## Author
- [cwmcfeely](https://github.com/cwmcfeely)