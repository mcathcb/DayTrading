"""
Day Trading Strategy Engine - Core Orchestrator
"""
import asyncio
import logging
from datetime import datetime, time
from typing import Dict, List, Optional
import pytz

from .data_layer import DataLayer
from .indicators import IndicatorEngine
from .strategies import MomentumBreakout, OptionsFlow
from .risk_manager import RiskManager
from .execution import ExecutionEngine
from .logger import TradeLogger

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

ET = pytz.timezone('America/New_York')
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

class TradingEngine:
    def __init__(self, config: dict):
        self.config = config
        self.tickers = config.get('tickers', ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA'])
        self.account_size = config.get('account_size', 25000)
        self.max_risk_pct = config.get('max_risk_pct', 0.02)
        self.max_daily_loss = config.get('max_daily_loss', 0.05)
        self.min_volume = config.get('min_volume', 500000)
        self.running = False
        self.daily_loss = 0.0
        self.shutoff_triggered = False
        self.signals: List[dict] = []
        self.open_positions: Dict[str, dict] = {}
        self.trade_history: List[dict] = []

        # Initialize layers
        self.data = DataLayer(config)
        self.indicators = IndicatorEngine()
        self.risk = RiskManager(
            account_size=self.account_size,
            max_risk_pct=self.max_risk_pct,
            max_daily_loss=self.max_daily_loss
        )
        self.execution = ExecutionEngine(config)
        self.trade_logger = TradeLogger(config.get('log_path', 'trades.db'))

        # Strategies
        self.strategies = [
            MomentumBreakout(config),
            OptionsFlow(config),
        ]

    def is_market_hours(self) -> bool:
        now = datetime.now(ET).time()
        return MARKET_OPEN <= now <= MARKET_CLOSE

    def check_daily_shutoff(self) -> bool:
        max_loss = self.account_size * self.max_daily_loss
        if self.daily_loss >= max_loss:
            if not self.shutoff_triggered:
                logger.warning(f"⚠️ Daily loss limit hit: ${self.daily_loss:.2f}. AUTO-SHUTOFF ACTIVATED.")
                self.shutoff_triggered = True
                self.close_all_positions()
            return True
        return False

    def close_all_positions(self):
        for ticker, pos in list(self.open_positions.items()):
            logger.info(f"Emergency close: {ticker}")
            self.execution.close_position(pos)
            self.open_positions.pop(ticker, None)

    async def scan_tick(self):
        if not self.is_market_hours():
            logger.info("Outside market hours. Waiting...")
            return

        if self.check_daily_shutoff():
            return

        all_signals = []
        for ticker in self.tickers:
            try:
                ohlcv = self.data.get_ohlcv(ticker, period='1d', interval='5m')
                if ohlcv is None or len(ohlcv) < 20:
                    continue

                # Volume filter
                avg_vol = ohlcv['volume'].tail(20).mean()
                if avg_vol < self.min_volume:
                    logger.debug(f"{ticker}: Volume too low ({avg_vol:.0f})")
                    continue

                # Calculate indicators
                enriched = self.indicators.calculate_all(ohlcv)

                # Earnings filter
                if self.data.has_upcoming_earnings(ticker, days=1):
                    logger.debug(f"{ticker}: Earnings blackout")
                    continue

                # Run each strategy
                for strategy in self.strategies:
                    signal = strategy.evaluate(ticker, enriched, self.data)
                    if signal:
                        signal['timestamp'] = datetime.now(ET).isoformat()
                        signal['ticker'] = ticker
                        # Risk sizing
                        sizing = self.risk.size_position(
                            entry=signal['entry'],
                            stop=signal['stop_loss'],
                            account=self.account_size - self.daily_loss
                        )
                        signal['shares'] = sizing['shares']
                        signal['dollar_risk'] = sizing['dollar_risk']
                        all_signals.append(signal)
                        logger.info(f"🔔 SIGNAL: {signal}")

            except Exception as e:
                logger.error(f"Error scanning {ticker}: {e}")

        self.signals = all_signals

        # Execute top-ranked signals
        for signal in all_signals[:3]:
            if signal['ticker'] not in self.open_positions:
                order = self.execution.place_order(signal)
                if order:
                    self.open_positions[signal['ticker']] = {**signal, 'order': order}
                    self.trade_logger.log_trade(signal)

        # Update open positions
        self.update_positions()

    def update_positions(self):
        for ticker, pos in list(self.open_positions.items()):
            quote = self.data.get_quote(ticker)
            if not quote:
                continue
            current_price = quote['price']
            pos['current_price'] = current_price
            pnl = (current_price - pos['entry']) * pos.get('shares', 1)
            if pos.get('direction') in ('put', 'short'):
                pnl = -pnl
            pos['unrealized_pnl'] = pnl

            # Auto stop-loss check
            if pos.get('direction') in ('call', 'long'):
                if current_price <= pos['stop_loss']:
                    logger.info(f"🛑 Stop hit for {ticker} at {current_price}")
                    self.execution.close_position(pos)
                    self.daily_loss += abs(pnl) if pnl < 0 else 0
                    self.trade_history.append({**pos, 'exit_price': current_price, 'pnl': pnl})
                    self.trade_logger.log_exit(pos, current_price, pnl)
                    self.open_positions.pop(ticker, None)
                elif current_price >= pos['target']:
                    logger.info(f"🎯 Target hit for {ticker} at {current_price}")
                    self.execution.close_position(pos)
                    self.trade_history.append({**pos, 'exit_price': current_price, 'pnl': pnl})
                    self.trade_logger.log_exit(pos, current_price, pnl)
                    self.open_positions.pop(ticker, None)

    def get_dashboard_state(self) -> dict:
        total_pnl = sum(t.get('pnl', 0) for t in self.trade_history)
        wins = [t for t in self.trade_history if t.get('pnl', 0) > 0]
        win_rate = len(wins) / len(self.trade_history) if self.trade_history else 0
        unrealized = sum(p.get('unrealized_pnl', 0) for p in self.open_positions.values())

        return {
            'signals': self.signals,
            'open_positions': list(self.open_positions.values()),
            'trade_history': self.trade_history[-50:],
            'stats': {
                'total_pnl': total_pnl,
                'unrealized_pnl': unrealized,
                'daily_loss': self.daily_loss,
                'win_rate': win_rate,
                'total_trades': len(self.trade_history),
                'open_count': len(self.open_positions),
                'shutoff_triggered': self.shutoff_triggered,
                'is_market_hours': self.is_market_hours(),
            }
        }

    async def run(self, interval_seconds: int = 60):
        self.running = True
        logger.info("🚀 Trading Engine Started")
        while self.running:
            await self.scan_tick()
            await asyncio.sleep(interval_seconds)

    def stop(self):
        self.running = False
        self.close_all_positions()
        logger.info("⛔ Engine stopped. All positions closed.")
