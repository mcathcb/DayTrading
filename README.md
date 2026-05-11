# ⚡ APEX Day Trading Strategy Engine

A full-stack day trading system: **Python backend** (FastAPI + yfinance + pandas-ta) + **React dashboard**.

---

## 📁 Project Structure

```
day_trading_engine/
├── engine/
│   ├── __init__.py
│   ├── core.py           # TradingEngine orchestrator
│   ├── data_layer.py     # yfinance OHLCV + options chain fetching
│   ├── indicators.py     # EMA/RSI/VWAP/BB/ATR/MACD/VolumeProfile
│   ├── strategies.py     # MomentumBreakout + OptionsFlow strategies
│   ├── risk_manager.py   # Kelly/Fixed-fractional sizing, daily shutoff
│   ├── execution.py      # Alpaca + Tradier + paper trading
│   └── logger.py         # SQLite + CSV trade logger
├── api.py                # FastAPI web server (REST endpoints)
├── requirements.txt
└── README.md

dashboard/
└── trading_dashboard.jsx  # React UI
```

---

## 🚀 Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set environment variables
```bash
# For Alpaca (paper trading — FREE at alpaca.markets)
export ALPACA_KEY_ID="your_key"
export ALPACA_SECRET_KEY="your_secret"
export ALPACA_BASE_URL="https://paper-api.alpaca.markets"

# For Tradier (options + equities)
export TRADIER_TOKEN="your_token"
export TRADIER_ACCOUNT_ID="your_account_id"
```

### 3. Start the API server
```bash
cd day_trading_engine
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Run the React dashboard
Drop `trading_dashboard.jsx` into your React project or open `http://localhost:8000` if serving via FastAPI StaticFiles.

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard` | Full state: signals, positions, stats |
| GET | `/api/signals` | Active trade signals |
| GET | `/api/positions` | Open positions |
| GET | `/api/trades?limit=50` | Trade history |
| GET | `/api/stats` | Performance metrics |
| GET | `/api/options/{ticker}` | Unusual options activity |
| POST | `/api/engine/start` | Start scan loop |
| POST | `/api/engine/stop` | Stop + close all |
| POST | `/api/engine/scan` | Manual scan tick |
| POST | `/api/trade/manual` | Place manual trade |
| DELETE | `/api/position/{ticker}` | Close a position |

---

## 📊 Strategies

### 1. Momentum Breakout
**Entry conditions (bullish call):**
- EMA 9 > EMA 21 > EMA 50 (aligned)
- Price > VWAP
- Break above 20-bar resistance with 1.8× volume spike
- RSI 50–78, MACD histogram positive

**Signal outputs:** Direction, entry, target (+2×ATR), stop (−1×ATR), expiry recommendation, confidence score

### 2. Options Flow
**Entry conditions:**
- Unusual options activity: Vol/OI ratio ≥ 2×
- Call or put flow imbalance ≥ 65% directional
- IV in range 0.20–2.00 (avoids hyper-IV gamma traps)
- Corroborated by price action (above/below VWAP)

**Signal outputs:** Direction from dominant flow, top IV, vol/OI ratio, 7–21 DTE expiry

---

## ⚙️ Configuration

Edit `DEFAULT_CONFIG` in `api.py`:

```python
{
  'tickers':       ['SPY','QQQ','AAPL','TSLA','NVDA','AMD','META','MSFT'],
  'account_size':  25000,
  'max_risk_pct':  0.02,   # 2% per trade
  'max_daily_loss': 0.05,  # 5% daily shutoff
  'min_volume':    500000,
  'broker':        'paper', # 'alpaca' | 'tradier' | 'paper'
  'sizing_method': 'fixed_fractional', # or 'kelly'
  'log_path':      'trades.db',
}
```

---

## 🛡️ Risk Management

| Feature | Default |
|---------|---------|
| Max risk per trade | 2% of account |
| Daily loss auto-shutoff | 5% of account |
| Position sizing | Fixed fractional (Kelly available) |
| Stop-loss enforcement | Auto on every position |
| Earnings blackout | 1 day before/after |
| Market hours filter | 9:30–4:00 ET only |

---

## 📈 Technical Indicators

| Indicator | Config |
|-----------|--------|
| EMA | 9 / 21 / 50 |
| RSI | 14-period |
| VWAP | Intraday cumulative |
| Bollinger Bands | 20-period, 2σ |
| ATR | 14-period |
| MACD | 12/26/9 |
| Volume Profile | POC + Value Area |

---

## 💾 Data Persistence

- **SQLite** (`trades.db`): Full trade history, open/closed status, daily summaries
- **CSV** (`trades_trades.csv`): Trade log for spreadsheet backtesting

```sql
-- Example query: today's closed trades
SELECT ticker, direction, entry, exit_price, pnl 
FROM trades 
WHERE DATE(timestamp) = DATE('now') AND status = 'closed'
ORDER BY pnl DESC;
```

---

## 🔧 Adding Custom Strategies

```python
# engine/strategies.py
class MyStrategy(BaseStrategy):
    name = "my_strategy"
    
    def evaluate(self, ticker, df, data_layer):
        ind = IndicatorEngine()
        row = ind.latest(df)
        
        if my_condition(row):
            return {
                'strategy': self.name,
                'direction': 'call',  # or 'put'
                'entry': row['close'],
                'target': row['close'] * 1.02,
                'stop_loss': row['close'] * 0.99,
                'confidence': 75,
                'expiry': self._expiry_recommendation(7),
            }
        return None

# Register in core.py
self.strategies = [MomentumBreakout(config), OptionsFlow(config), MyStrategy(config)]
```

---

## ⚠️ Disclaimer

This software is for **educational and paper trading purposes**. Day trading involves substantial risk of loss. Past performance does not guarantee future results. Always use paper trading to validate strategies before risking real capital.
