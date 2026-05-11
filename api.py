"""
FastAPI Web Server
Exposes REST endpoints consumed by the React dashboard.
Runs the trading engine in background via AsyncIO.
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Engine imports (adjust path as needed)
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from engine.core import TradingEngine
from engine.logger import TradeLogger

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    'tickers': ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA', 'AMD', 'META', 'MSFT'],
    'account_size': 25000,
    'max_risk_pct': 0.02,
    'max_daily_loss': 0.05,
    'min_volume': 500000,
    'broker': 'paper',
    'log_path': 'trades.db',
    'sizing_method': 'fixed_fractional',
    # Broker credentials from env
    'alpaca_key': os.getenv('ALPACA_KEY_ID'),
    'alpaca_secret': os.getenv('ALPACA_SECRET_KEY'),
    'alpaca_url': os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets'),
    'tradier_token': os.getenv('TRADIER_TOKEN'),
    'tradier_account_id': os.getenv('TRADIER_ACCOUNT_ID'),
}

engine: Optional[TradingEngine] = None
trade_logger: Optional[TradeLogger] = None
scan_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, trade_logger
    engine = TradingEngine(DEFAULT_CONFIG)
    trade_logger = engine.trade_logger
    logger.info("Trading engine initialized")
    yield
    if engine:
        engine.stop()


app = FastAPI(title="Day Trading Engine", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ────────────────────────────────────────────────────────────────────
class EngineConfig(BaseModel):
    tickers: list[str] = DEFAULT_CONFIG['tickers']
    account_size: float = 25000
    max_risk_pct: float = 0.02
    max_daily_loss: float = 0.05
    broker: str = 'paper'


class ManualSignal(BaseModel):
    ticker: str
    direction: str
    entry: float
    stop_loss: float
    target: float
    shares: int = 1


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "ok", "service": "Day Trading Engine", "time": datetime.now().isoformat()}


@app.get("/api/dashboard")
async def get_dashboard():
    """Full dashboard state: signals, positions, stats."""
    if not engine:
        raise HTTPException(503, "Engine not initialized")
    return engine.get_dashboard_state()


@app.get("/api/signals")
async def get_signals():
    """Latest trading signals."""
    if not engine:
        raise HTTPException(503, "Engine not ready")
    return {"signals": engine.signals, "count": len(engine.signals)}


@app.get("/api/positions")
async def get_positions():
    """Current open positions."""
    if not engine:
        raise HTTPException(503, "Engine not ready")
    return {"positions": list(engine.open_positions.values())}


@app.get("/api/trades")
async def get_trades(limit: int = 50, status: str = None):
    """Trade history from DB."""
    if not trade_logger:
        return {"trades": []}
    return {"trades": trade_logger.get_trades(limit=limit, status=status)}


@app.get("/api/stats")
async def get_stats():
    """Performance statistics."""
    if not engine or not trade_logger:
        return {}
    perf = trade_logger.get_performance_stats()
    risk = engine.risk.get_stats()
    dashboard = engine.get_dashboard_state()['stats']
    return {**perf, **risk, **dashboard}


@app.get("/api/daily-summary")
async def get_daily_summary(days: int = 30):
    if not trade_logger:
        return {"summary": []}
    return {"summary": trade_logger.get_daily_summary(days=days)}


@app.post("/api/engine/start")
async def start_engine(background_tasks: BackgroundTasks):
    """Start the scan loop."""
    global scan_task
    if engine and not engine.running:
        background_tasks.add_task(engine.run, 60)
        return {"status": "started"}
    return {"status": "already_running"}


@app.post("/api/engine/stop")
async def stop_engine():
    """Stop the scan loop and close positions."""
    if engine:
        engine.stop()
        return {"status": "stopped"}
    return {"status": "not_running"}


@app.post("/api/engine/scan")
async def manual_scan():
    """Trigger a single scan tick immediately."""
    if not engine:
        raise HTTPException(503, "Engine not ready")
    await engine.scan_tick()
    return {"status": "scanned", "signals": engine.signals}


@app.post("/api/trade/manual")
async def place_manual_trade(signal: ManualSignal):
    """Place a manual trade signal."""
    if not engine:
        raise HTTPException(503, "Engine not ready")
    sig_dict = signal.model_dump()
    sig_dict['timestamp'] = datetime.now().isoformat()
    sig_dict['strategy'] = 'manual'
    sig_dict['confidence'] = 100
    order = engine.execution.place_order(sig_dict)
    if order:
        engine.open_positions[signal.ticker] = {**sig_dict, 'order': order}
        engine.trade_logger.log_trade(sig_dict)
        return {"status": "placed", "order": order}
    raise HTTPException(500, "Order placement failed")


@app.delete("/api/position/{ticker}")
async def close_position(ticker: str):
    """Manually close a position."""
    if not engine:
        raise HTTPException(503, "Engine not ready")
    pos = engine.open_positions.get(ticker)
    if not pos:
        raise HTTPException(404, f"No open position for {ticker}")
    engine.execution.close_position(pos)
    engine.open_positions.pop(ticker, None)
    return {"status": "closed", "ticker": ticker}


@app.get("/api/options/{ticker}")
async def get_options(ticker: str):
    """Unusual options activity for a ticker."""
    if not engine:
        raise HTTPException(503, "Engine not ready")
    unusual = engine.data.get_unusual_options_activity(ticker)
    if unusual is None:
        return {"ticker": ticker, "unusual": []}
    return {"ticker": ticker, "unusual": unusual.head(20).to_dict(orient='records')}


@app.get("/api/config")
async def get_config():
    """Current engine configuration (sanitized)."""
    safe = {k: v for k, v in DEFAULT_CONFIG.items()
            if k not in ('alpaca_key', 'alpaca_secret', 'tradier_token')}
    return safe


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
