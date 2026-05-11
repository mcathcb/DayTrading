"""
Execution Engine
Supports: Alpaca (equities + paper trading), Tradier (options + equities)
Handles: market/limit orders, stop-loss, partial fills, position tracking
"""
import logging
import os
from typing import Optional, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class ExecutionEngine:
    def __init__(self, config: dict):
        self.broker = config.get('broker', 'paper')  # 'alpaca', 'tradier', 'paper'
        self.config = config
        self._alpaca = None
        self._tradier_headers = None
        self.open_orders: Dict[str, dict] = {}

        if self.broker == 'alpaca':
            self._init_alpaca()
        elif self.broker == 'tradier':
            self._init_tradier()
        else:
            logger.info("📋 Paper trading mode active.")

    # ── Alpaca Init ───────────────────────────────────────────────────────────
    def _init_alpaca(self):
        try:
            import alpaca_trade_api as tradeapi
            self._alpaca = tradeapi.REST(
                key_id=self.config.get('alpaca_key') or os.getenv('ALPACA_KEY_ID'),
                secret_key=self.config.get('alpaca_secret') or os.getenv('ALPACA_SECRET_KEY'),
                base_url=self.config.get('alpaca_url', 'https://paper-api.alpaca.markets'),
                api_version='v2'
            )
            account = self._alpaca.get_account()
            logger.info(f"✅ Alpaca connected | Equity: ${account.equity} | Status: {account.status}")
        except ImportError:
            logger.error("alpaca-trade-api not installed. Run: pip install alpaca-trade-api")
            self.broker = 'paper'
        except Exception as e:
            logger.error(f"Alpaca init error: {e}")
            self.broker = 'paper'

    # ── Tradier Init ──────────────────────────────────────────────────────────
    def _init_tradier(self):
        token = self.config.get('tradier_token') or os.getenv('TRADIER_TOKEN')
        if not token:
            logger.error("No Tradier token found.")
            self.broker = 'paper'
            return
        self._tradier_headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json'
        }
        self._tradier_base = self.config.get(
            'tradier_url', 'https://sandbox.tradier.com/v1'
        )
        logger.info("✅ Tradier configured.")

    # ── Place Order ───────────────────────────────────────────────────────────
    def place_order(self, signal: dict) -> Optional[dict]:
        ticker = signal['ticker']
        direction = signal['direction']
        shares = signal.get('shares', 1)
        entry = signal['entry']
        stop = signal['stop_loss']
        strategy = signal.get('strategy', '')

        try:
            if self.broker == 'alpaca':
                return self._alpaca_order(ticker, direction, shares, entry, stop)
            elif self.broker == 'tradier':
                return self._tradier_order(ticker, direction, shares, entry, stop, signal)
            else:
                return self._paper_order(ticker, direction, shares, entry, stop, signal)
        except Exception as e:
            logger.error(f"Order placement error for {ticker}: {e}")
            return None

    def _alpaca_order(self, ticker, direction, shares, entry, stop) -> dict:
        side = 'buy' if direction in ('call', 'long') else 'sell'
        try:
            order = self._alpaca.submit_order(
                symbol=ticker,
                qty=shares,
                side=side,
                type='limit',
                limit_price=round(entry, 2),
                time_in_force='day',
            )
            # Set bracket stop-loss
            self._alpaca.submit_order(
                symbol=ticker,
                qty=shares,
                side='sell' if side == 'buy' else 'buy',
                type='stop',
                stop_price=round(stop, 2),
                time_in_force='gtc',
            )
            logger.info(f"🟢 Alpaca order placed: {side} {shares}x {ticker} @ {entry}")
            return {
                'order_id': order.id,
                'status': order.status,
                'broker': 'alpaca',
                'timestamp': str(order.submitted_at),
            }
        except Exception as e:
            logger.error(f"Alpaca order error: {e}")
            return None

    def _tradier_order(self, ticker, direction, shares, entry, stop, signal) -> dict:
        import requests
        account_id = self.config.get('tradier_account_id') or os.getenv('TRADIER_ACCOUNT_ID')
        url = f"{self._tradier_base}/accounts/{account_id}/orders"

        # Check if this is an options signal
        if signal.get('expiry') and signal.get('strategy') == 'options_flow':
            # Build option symbol (OCC format): TICKER + YYMMDD + C/P + Strike*1000
            expiry = signal['expiry'].replace('-', '')[2:]  # YYMMDD
            opt_type = 'C' if direction == 'call' else 'P'
            strike = int(round(entry / 5) * 5)  # round to nearest $5 strike
            option_symbol = f"{ticker}{expiry}{opt_type}{strike:08d}"
            data = {
                'class': 'option',
                'symbol': ticker,
                'option_symbol': option_symbol,
                'side': 'buy_to_open',
                'quantity': max(1, shares // 100),
                'type': 'limit',
                'price': round(entry * 0.03, 2),  # ~3% of stock price as rough premium
                'duration': 'day',
            }
        else:
            side = 'buy' if direction in ('call', 'long') else 'sell_short'
            data = {
                'class': 'equity',
                'symbol': ticker,
                'side': side,
                'quantity': shares,
                'type': 'limit',
                'price': round(entry, 2),
                'duration': 'day',
            }

        resp = requests.post(url, headers=self._tradier_headers, data=data)
        result = resp.json()
        logger.info(f"🟢 Tradier order: {result}")
        return {'order_id': result.get('order', {}).get('id'), 'broker': 'tradier', 'raw': result}

    def _paper_order(self, ticker, direction, shares, entry, stop, signal) -> dict:
        order_id = f"paper_{ticker}_{datetime.now().strftime('%H%M%S%f')}"
        order = {
            'order_id': order_id,
            'status': 'filled',
            'broker': 'paper',
            'fill_price': entry,
            'shares': shares,
            'direction': direction,
            'timestamp': datetime.now().isoformat(),
        }
        self.open_orders[order_id] = order
        logger.info(f"📋 Paper order: {direction} {shares}x {ticker} @ ${entry:.2f} | Stop: ${stop:.2f}")
        return order

    # ── Close Position ────────────────────────────────────────────────────────
    def close_position(self, position: dict) -> Optional[dict]:
        ticker = position.get('ticker')
        shares = position.get('shares', 1)
        direction = position.get('direction')

        if self.broker == 'alpaca' and self._alpaca:
            try:
                side = 'sell' if direction in ('call', 'long') else 'buy'
                order = self._alpaca.submit_order(
                    symbol=ticker, qty=shares, side=side,
                    type='market', time_in_force='day'
                )
                logger.info(f"🔴 Closed {ticker} via Alpaca")
                return {'order_id': order.id, 'status': 'closing'}
            except Exception as e:
                logger.error(f"Close error: {e}")
        else:
            logger.info(f"📋 Paper close: {ticker}")
            return {'status': 'paper_closed', 'ticker': ticker}

    # ── Account Info ──────────────────────────────────────────────────────────
    def get_account_info(self) -> dict:
        if self.broker == 'alpaca' and self._alpaca:
            try:
                acc = self._alpaca.get_account()
                return {
                    'equity': float(acc.equity),
                    'buying_power': float(acc.buying_power),
                    'cash': float(acc.cash),
                    'status': acc.status,
                }
            except Exception as e:
                logger.error(f"Account info error: {e}")
        return {'equity': 0, 'buying_power': 0, 'cash': 0, 'status': 'paper'}

    def get_open_positions(self) -> list:
        if self.broker == 'alpaca' and self._alpaca:
            try:
                positions = self._alpaca.list_positions()
                return [
                    {
                        'ticker': p.symbol,
                        'shares': int(p.qty),
                        'entry': float(p.avg_entry_price),
                        'current_price': float(p.current_price),
                        'unrealized_pnl': float(p.unrealized_pl),
                        'market_value': float(p.market_value),
                    }
                    for p in positions
                ]
            except Exception as e:
                logger.error(f"Get positions error: {e}")
        return []
