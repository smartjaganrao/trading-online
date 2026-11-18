# ⚡ Trading Online - Institutional Algorithmic Trading Platform & AI Agent

[![Python](https://img.shields.io/badge/Python-3.14%2B-blue.svg)](https://www.python.org/)
[![Package Manager](https://img.shields.io/badge/uv-fast%20python-purple.svg)](https://github.com/astral-sh/uv)
[![Broker](https://img.shields.io/badge/Zerodha-KiteConnect-orange.svg)](https://kite.trade/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An institutional-grade algorithmic trading system, quantitative execution engine, and terminal dashboard designed specifically for Indian markets (**NSE & BSE**). Engineered with strict capital protection protocols, statistical regime filters, and comprehensive transaction friction modeling to overcome the pitfalls where 90%+ of retail algorithmic traders fail.

---

## 🏛️ The Institutional Philosophy: Beating the 90% Failure Rate

Regulatory audits (such as SEBI's study on retail F&O) reveal that **over 88% to 93% of retail traders lose money**, with institutional algorithmic desks capturing virtually all market profits. This codebase addresses the three primary structural causes of retail algo failure:

| Failure Root Cause | How Typical Retail Bots Fail | How This Platform Solves It |
| :--- | :--- | :--- |
| **Consolidation Whipsaws** | Trend indicators (SuperTrend/EMA) trigger repeated false breakouts in sideways chop. | **ADX & Choppiness Regime Gate**: Blocks trend entries if $\text{ADX} < 22$ or $\text{CHOP} \ge 61.8$. |
| **Midday False Liquidity** | Low-volume periods (11:30 AM – 1:30 PM IST) generate whipsaws. | **Midday No-Trade Window**: Automatically pauses new entry signals during low-volume hours. |
| **Friction & Phantom Profits** | Paper profits turn negative after brokerage, STT, and slippage. | **Statutory Cost Engine**: Accurately accounts for Zerodha brokerage (₹20), STT, GST, SEBI fee, and 0.04% slippage. |
| **Runaway Drawdowns** | Revenge trading or lack of hard stops wipes accounts in single sessions. | **Capital Circuit Breaker**: Hard daily loss lock (e.g. ₹1,000 / 2%) + strict 1-lot sizing + 3:15 PM EOD square-off. |

---

## 🚀 Key Architectural Features

1. **Dual-Mode Execution Architecture**:
   * **Paper Trading (Default)**: Zero-risk simulated execution with virtual margin, live price tracking, simulated fills, and realistic transaction cost deductions.
   * **Live Zerodha Kite Execution**: Direct authenticated integration with Zerodha's KiteConnect API with pre-flight risk checks.

2. **Statistical Regime & Trend Confluence Strategy (`strategies/supertrend_ema.py`)**:
   * **SuperTrend (10, 3)**: Primary directional trend filter.
   * **Dual EMA (9, 21)**: Exponential moving average crossover for short-term momentum bias.
   * **RSI (14)**: Momentum exhaustion filter (avoids buying overbought $>75$ or selling oversold $<25$).
   * **ADX (14) & Choppiness Index (14)**: Quantitative gate preventing trades in rangebound markets.

3. **Institutional Risk Engine (`core/risk_manager.py`)**:
   * **Daily Circuit Breaker**: Auto-halts all trading for the day if cumulative loss breaches the threshold.
   * **Strict Lot Sizing**: Enforces 1-lot validation rule during strategy development.
   * **Dynamic Trailing Stops**: Automatically calculates 1:2 R:R stop-loss and profit targets on entry, with trailing profit locks in trending sessions.
   * **Mandatory 3:15 PM EOD Square-Off**: Closes open intraday positions before market close to avoid overnight gap risk and option decay.

4. **Real Statutory Friction & Slippage Engine (`execution/journal.py`)**:
   * Automatically calculates and logs:
     * Brokerage (Zerodha ₹20 flat / 0.03%)
     * Securities Transaction Tax (STT)
     * Exchange Turnover & SEBI Charges
     * Stamp Duty & GST (18%)
     * Bid-Ask Slippage drag (0.04%)
   * Logs gross P&L, statutory fees, and net realized P&L directly to `data/trades.csv`.

5. **Continuous Market Learner & Strategy Memory (`core/market_learner.py`)**:
   * Post-market AI analysis extracting empirical lessons from executed trades.
   * Automatically updates `data/market_memory.json` and human-readable `data/learning_journal.md`.

6. **Interactive Terminal Dashboard (`main.py`)**:
   * Live visual portfolio status, margin usage, active positions, and real-time signals powered by `rich`.

---

## 🛠️ Quick Start

### 1. Installation

This project uses [`uv`](https://github.com/astral-sh/uv) for lightning-fast, reproducible dependency management:

```bash
# Clone the repository
git clone https://github.com/smartjaganrao/trading-online.git
cd trading-online

# Sync virtual environment and dependencies
uv sync
```

### 2. Environment Setup

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Default configuration runs in **Paper Trading Mode** (zero risk):
```env
PAPER_TRADING=True
PAPER_INITIAL_CAPITAL=100000.0
MAX_DAILY_LOSS=1000.0
MAX_LOTS=1
ENABLE_MIDDAY_FILTER=True
MIDDAY_START=11:30
MIDDAY_END=13:30
ADX_THRESHOLD=22.0
CHOP_THRESHOLD=61.8
```

---

## 💻 CLI Commands & Usage

### 1. Account & Margin Status
Check current cash, utilized margin, and risk circuit limits:
```bash
uv run python main.py --status
```

### 2. Run Paper Trading Simulation
Simulate live ticks, strategy signal evaluation, and automated trade execution:
```bash
uv run python main.py --ticks 15
```

### 3. Full-Day Intraday Simulation (09:15 to 15:15 IST)
Simulate a complete 72-candle intraday trading session:
```bash
uv run python main.py --day
```

### 4. Power Hour Aggressive Execution (2:45 to 3:15 PM)
Simulate high-gamma momentum trading with trailing profit locks during the market close:
```bash
uv run python main.py --power-hour
```

### 5. AI Chief Risk Officer (CRO) Monitor
Activate the real-time sentinel to monitor volatility extremes and stop-loss proximity:
```bash
uv run python main.py --monitor
```

### 6. Post-Market Learning & Strategy Evolution
Analyze today's trades, calculate net friction costs, extract lessons, and update strategy memory:
```bash
uv run python main.py --learn
```

---

## 🔐 Connecting Zerodha Kite (Live Trading)

1. Set your Zerodha developer API credentials in `.env`:
   ```env
   PAPER_TRADING=False
   KITE_API_KEY=your_kite_api_key
   KITE_API_SECRET=your_kite_api_secret
   KITE_USER_ID=your_zerodha_user_id
   ```
2. Generate login URL:
   ```bash
   uv run python main.py --login
   ```
3. Open the link in your browser, log in, and copy the `request_token` from the redirect URL.
4. Complete authentication:
   ```bash
   uv run python main.py --token <YOUR_REQUEST_TOKEN>
   ```
   *(Session token is automatically cached for the day in `.kite_session.json`)*.

---

## 📁 Repository Structure

```
trading-online/
├── .env.example          # Sample configuration template
├── .gitignore            # Security exclusions (.env, credentials, session tokens)
├── pyproject.toml        # Dependencies and metadata
├── uv.lock               # Deterministic lockfile
├── README.md             # Documentation and usage guide
├── config/
│   └── settings.py       # Pydantic environment configuration
├── core/
│   ├── auth.py           # Zerodha KiteConnect session & token manager
│   ├── client.py         # PaperTradingClient & KiteLiveClient abstraction
│   ├── risk_manager.py   # Circuit breaker, lot sizing & midday time gate
│   ├── expert_monitor.py # AI Chief Risk Officer sentinel monitor
│   └── market_learner.py # Post-market learning & strategy memory engine
├── strategies/
│   ├── base.py           # Base strategy interface
│   └── supertrend_ema.py # SuperTrend + EMA + RSI + ADX/CHOP confluence strategy
├── execution/
│   ├── journal.py        # Statutory cost & slippage engine + trade logger
│   ├── day_simulator.py  # 72-candle full-day intraday simulator
│   ├── power_hour.py     # 2:45 PM high-volatility momentum execution
│   └── backtester.py     # Historical backtesting module
└── data/
    ├── trades.csv        # Detailed audit trail of entries, exits, and P&L
    ├── market_memory.json# Persistent quantitative memory
    └── learning_journal.md# Markdown journal of empirical trading lessons
```

---

## ⚠️ Disclaimer & Risk Disclosure

* **Educational & Research Purpose**: This software is intended for educational, quantitative research, and paper-trading simulation purposes.
* **Financial Risk**: Trading derivatives (Futures & Options) and equities involves substantial risk of financial loss. Ensure you thoroughly validate any systematic strategy on paper before deploying real capital.
* **Regulatory Compliance**: Follow all applicable rules and guidelines specified by SEBI and your respective broker when executing automated orders.

---

## 📄 License

Distributed under the [MIT License](LICENSE).
