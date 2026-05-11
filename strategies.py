"""
Trading Strategies
 1. MomentumBreakout — EMA-aligned volume breakout above resistance
 2. OptionsFlow     — unusual options activity as directional signals
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
import numpy as np

from .indicators import IndicatorEngine

logger = logging.getLogger(__name__)


class BaseStrategy:
    name = "base"

    def __init__(self, config: dict):
        self.config = config

    def evaluate(self, ticker: str, df: pd.DataFrame, data_layer) -> Optional[dict]:
        raise NotImplementedError

    def _expiry_recommendation(self, days_out: int = 7) -> str:
        from datetime import datetime, timedelta
        target = datetime.now() + timedelta(days=days_out)
        # Round to next Friday
        while target.weekday() != 4:
            target += timedelta(days=1)
        return target.strftime('%Y-%m-%d')


# ─────────────────────────────────────────────────────────────────────────────
#  STRATEGY 1: Momentum Breakout
# ─────────────────────────────────────────────────────────────────────────────
class MomentumBreakout(BaseStrategy):
    """
    Entry conditions (bullish):
      - EMA 9 > EMA 21 > EMA 50 (aligned bullish)
      - Price above VWAP
      - Current bar breaks above 20-day resistance (recent swing high)
      - Volume spike (2x 20-bar avg)
      - RSI 50–75 (momentum but not overbought)
      - MACD histogram positive and rising

    Signal output: direction=call, entry, target (+2×ATR), stop (−1×ATR),
                   expiry 7–14 DTE, confidence score
    """
    name = "momentum_breakout"

    def evaluate(self, ticker: str, df: pd.DataFrame, data_layer) -> Optional[dict]:
        try:
            if len(df) < 21:
                return None

            ind = IndicatorEngine()
            row = ind.latest(df)
            price = row['close']
            atr = row.get('atr', price * 0.01)

            # Resistance from recent swing highs (20-bar lookback)
            resistance = df['high'].rolling(20).max().iloc[-2]  # -2 avoids current bar

            # ── Bullish Breakout ──────────────────────────────────────────────
            bullish = (
                ind.ema_aligned_bullish(df) and
                ind.above_vwap(df) and
                ind.volume_spike(df, multiplier=1.8) and
                price > resistance and
                50 <= row.get('rsi', 50) <= 78 and
                row.get('macd_hist', 0) > 0
            )

            # ── Bearish Breakdown (for puts) ──────────────────────────────────
            support = df['low'].rolling(20).min().iloc[-2]
            bearish = (
                ind.ema_aligned_bearish(df) and
                not ind.above_vwap(df) and
                ind.volume_spike(df, multiplier=1.8) and
                price < support and
                22 <= row.get('rsi', 50) <= 50 and
                row.get('macd_hist', 0) < 0
            )

            if not bullish and not bearish:
                return None

            direction = 'call' if bullish else 'put'
            sign = 1 if bullish else -1

            target = price + sign * 2.0 * atr
            stop = price - sign * 1.0 * atr

            # Confidence score 0–100
            confidence = 0
            if ind.ema_aligned_bullish(df) if bullish else ind.ema_aligned_bearish(df):
                confidence += 30
            if ind.above_vwap(df) if bullish else not ind.above_vwap(df):
                confidence += 20
            if ind.volume_spike(df, 2.0):
                confidence += 25
            if row.get('macd_hist', 0) != 0:
                confidence += 15
            rsi = row.get('rsi', 50)
            if (55 < rsi < 70 and bullish) or (30 < rsi < 45 and bearish):
                confidence += 10

            return {
                'strategy': self.name,
                'direction': direction,
                'entry': round(price, 2),
                'target': round(target, 2),
                'stop_loss': round(stop, 2),
                'risk_reward': round(abs(target - price) / abs(price - stop), 2) if abs(price - stop) > 0 else 0,
                'atr': round(atr, 2),
                'rsi': round(rsi, 1),
                'resistance': round(resistance, 2),
                'expiry': self._expiry_recommendation(7),
                'confidence': min(confidence, 100),
                'indicators': {
                    'ema_9': round(row.get('ema_9', 0), 2),
                    'ema_21': round(row.get('ema_21', 0), 2),
                    'ema_50': round(row.get('ema_50', 0), 2),
                    'vwap': round(row.get('vwap', 0), 2),
                    'macd_hist': round(row.get('macd_hist', 0), 4),
                    'bb_upper': round(row.get('bb_upper', 0), 2),
                    'bb_lower': round(row.get('bb_lower', 0), 2),
                }
            }

        except Exception as e:
            logger.error(f"MomentumBreakout error on {ticker}: {e}")
            return None


# ─────────────────────────────────────────────────────────────────────────────
#  STRATEGY 2: Options Flow
# ─────────────────────────────────────────────────────────────────────────────
class OptionsFlow(BaseStrategy):
    """
    Entry conditions:
      - Unusual options activity: Vol/OI ratio >= 2×
      - IV rank filtering (high IV relative to 52-week range = premium sell,
        low IV = directional buy signal)
      - Call/put flow imbalance → directional bias
      - Corroborate with price action above/below VWAP

    Signal output: direction=call/put based on dominant flow, DTE 7–21,
                   entry at current price, stops 1.5×ATR
    """
    name = "options_flow"
    MIN_VOL_OI = 2.0
    MIN_IV = 0.20
    MAX_IV = 2.0   # avoid gamma traps on hyper-IV names

    def evaluate(self, ticker: str, df: pd.DataFrame, data_layer) -> Optional[dict]:
        try:
            unusual = data_layer.get_unusual_options_activity(ticker, vol_oi_ratio=self.MIN_VOL_OI)
            if unusual is None or unusual.empty:
                return None

            # Filter IV range
            unusual = unusual[
                (unusual['impliedvolatility'] >= self.MIN_IV) &
                (unusual['impliedvolatility'] <= self.MAX_IV)
            ]
            if unusual.empty:
                return None

            # Aggregate call vs put volume
            call_vol = unusual[unusual['type'] == 'call']['volume'].sum()
            put_vol = unusual[unusual['type'] == 'put']['volume'].sum()
            total = call_vol + put_vol
            if total == 0:
                return None

            call_ratio = call_vol / total
            put_ratio = put_vol / total

            # Need at least 65/35 imbalance
            if max(call_ratio, put_ratio) < 0.65:
                return None

            direction = 'call' if call_ratio > put_ratio else 'put'

            # Corroborate with price action
            ind = IndicatorEngine()
            row = ind.latest(df)
            price = row['close']
            above_vwap = ind.above_vwap(df)

            # Don't fade strong divergence
            if direction == 'call' and not above_vwap:
                return None
            if direction == 'put' and above_vwap:
                return None

            atr = row.get('atr', price * 0.01)
            sign = 1 if direction == 'call' else -1

            # Get top unusual contract
            top = unusual.iloc[0]
            iv = float(top.get('impliedvolatility', 0.3))
            vol_oi = float(top.get('vol_oi_ratio', self.MIN_VOL_OI))
            best_expiry = str(top.get('expiry', self._expiry_recommendation(14)))

            # Confidence
            confidence = 40
            if vol_oi >= 5.0:
                confidence += 25
            elif vol_oi >= 3.0:
                confidence += 15
            if (direction == 'call' and above_vwap) or (direction == 'put' and not above_vwap):
                confidence += 20
            if call_ratio > 0.80 or put_ratio > 0.80:
                confidence += 15

            return {
                'strategy': self.name,
                'direction': direction,
                'entry': round(price, 2),
                'target': round(price + sign * 2.5 * atr, 2),
                'stop_loss': round(price - sign * 1.5 * atr, 2),
                'risk_reward': round(2.5 / 1.5, 2),
                'atr': round(atr, 2),
                'rsi': round(row.get('rsi', 50), 1),
                'expiry': best_expiry,
                'confidence': min(confidence, 100),
                'flow_data': {
                    'call_volume': int(call_vol),
                    'put_volume': int(put_vol),
                    'call_ratio': round(call_ratio, 2),
                    'top_vol_oi_ratio': round(vol_oi, 1),
                    'top_iv': round(iv, 3),
                    'unusual_contracts': len(unusual),
                },
                'indicators': {
                    'vwap': round(row.get('vwap', 0), 2),
                    'ema_9': round(row.get('ema_9', 0), 2),
                    'bb_upper': round(row.get('bb_upper', 0), 2),
                    'bb_lower': round(row.get('bb_lower', 0), 2),
                }
            }

        except Exception as e:
            logger.error(f"OptionsFlow error on {ticker}: {e}")
            return None
