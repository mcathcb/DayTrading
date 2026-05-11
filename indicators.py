"""
Indicator Engine
Calculates: EMA(9/21/50), RSI(14), VWAP, Bollinger Bands, ATR, MACD, Volume Profile
Uses pandas-ta for TA calculations (pure Python, no TA-Lib C dependency needed).
"""
import logging
import numpy as np
import pandas as pd
try:
    import pandas_ta as ta
    PANDAS_TA = True
except ImportError:
    PANDAS_TA = False
    logging.warning("pandas-ta not found, using manual calculations")

logger = logging.getLogger(__name__)


class IndicatorEngine:
    def calculate_all(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df = self._ema(df)
        df = self._rsi(df)
        df = self._vwap(df)
        df = self._bollinger(df)
        df = self._atr(df)
        df = self._macd(df)
        df = self._volume_profile(df)
        return df

    # ── EMA 9 / 21 / 50 ──────────────────────────────────────────────────────
    def _ema(self, df: pd.DataFrame) -> pd.DataFrame:
        for period in [9, 21, 50]:
            col = f'ema_{period}'
            if PANDAS_TA:
                df[col] = ta.ema(df['close'], length=period)
            else:
                df[col] = df['close'].ewm(span=period, adjust=False).mean()
        return df

    # ── RSI 14 ────────────────────────────────────────────────────────────────
    def _rsi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        if PANDAS_TA:
            df['rsi'] = ta.rsi(df['close'], length=period)
        else:
            delta = df['close'].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
            avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            df['rsi'] = 100 - (100 / (1 + rs))
        return df

    # ── VWAP (intraday, resets on session open) ───────────────────────────────
    def _vwap(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            typical = (df['high'] + df['low'] + df['close']) / 3
            cumvol = df['volume'].cumsum()
            cumtp = (typical * df['volume']).cumsum()
            df['vwap'] = cumtp / cumvol
        except Exception as e:
            logger.warning(f"VWAP error: {e}")
            df['vwap'] = np.nan
        return df

    # ── Bollinger Bands (20, 2σ) ──────────────────────────────────────────────
    def _bollinger(self, df: pd.DataFrame, period: int = 20, std: float = 2.0) -> pd.DataFrame:
        if PANDAS_TA:
            bb = ta.bbands(df['close'], length=period, std=std)
            if bb is not None:
                df['bb_lower'] = bb.iloc[:, 0]
                df['bb_mid'] = bb.iloc[:, 1]
                df['bb_upper'] = bb.iloc[:, 2]
        else:
            sma = df['close'].rolling(period).mean()
            sigma = df['close'].rolling(period).std()
            df['bb_mid'] = sma
            df['bb_upper'] = sma + std * sigma
            df['bb_lower'] = sma - std * sigma
        df['bb_width'] = (df.get('bb_upper', np.nan) - df.get('bb_lower', np.nan)) / df.get('bb_mid', np.nan)
        return df

    # ── ATR 14 ────────────────────────────────────────────────────────────────
    def _atr(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        if PANDAS_TA:
            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=period)
        else:
            high_low = df['high'] - df['low']
            high_close = (df['high'] - df['close'].shift()).abs()
            low_close = (df['low'] - df['close'].shift()).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df['atr'] = tr.ewm(com=period - 1, min_periods=period).mean()
        return df

    # ── MACD (12/26/9) ────────────────────────────────────────────────────────
    def _macd(self, df: pd.DataFrame) -> pd.DataFrame:
        if PANDAS_TA:
            macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
            if macd is not None:
                df['macd'] = macd.iloc[:, 0]
                df['macd_signal'] = macd.iloc[:, 2]
                df['macd_hist'] = macd.iloc[:, 1]
        else:
            ema12 = df['close'].ewm(span=12, adjust=False).mean()
            ema26 = df['close'].ewm(span=26, adjust=False).mean()
            df['macd'] = ema12 - ema26
            df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
            df['macd_hist'] = df['macd'] - df['macd_signal']
        return df

    # ── Volume Profile (price levels with most traded volume) ─────────────────
    def _volume_profile(self, df: pd.DataFrame, bins: int = 20) -> pd.DataFrame:
        try:
            price_range = np.linspace(df['low'].min(), df['high'].max(), bins + 1)
            vol_by_bin = np.zeros(bins)
            for i in range(len(df)):
                row = df.iloc[i]
                for b in range(bins):
                    if price_range[b] <= row['close'] < price_range[b + 1]:
                        vol_by_bin[b] += row['volume']
                        break
            poc_idx = np.argmax(vol_by_bin)
            df['vp_poc'] = (price_range[poc_idx] + price_range[poc_idx + 1]) / 2
            df['vp_value_area_high'] = price_range[min(poc_idx + 2, bins)]
            df['vp_value_area_low'] = price_range[max(poc_idx - 2, 0)]
        except Exception as e:
            logger.warning(f"Volume profile error: {e}")
            df['vp_poc'] = np.nan
        return df

    # ── Convenience accessors ─────────────────────────────────────────────────
    @staticmethod
    def latest(df: pd.DataFrame) -> pd.Series:
        return df.iloc[-1]

    @staticmethod
    def ema_aligned_bullish(df: pd.DataFrame) -> bool:
        """EMA 9 > 21 > 50 on latest bar."""
        row = df.iloc[-1]
        return row.get('ema_9', 0) > row.get('ema_21', 0) > row.get('ema_50', 0)

    @staticmethod
    def ema_aligned_bearish(df: pd.DataFrame) -> bool:
        row = df.iloc[-1]
        return row.get('ema_9', 9999) < row.get('ema_21', 9999) < row.get('ema_50', 9999)

    @staticmethod
    def above_vwap(df: pd.DataFrame) -> bool:
        row = df.iloc[-1]
        return row['close'] > row.get('vwap', 0)

    @staticmethod
    def volume_spike(df: pd.DataFrame, multiplier: float = 2.0) -> bool:
        """Current bar volume > multiplier * 20-bar avg."""
        avg_vol = df['volume'].iloc[-21:-1].mean()
        return df['volume'].iloc[-1] > avg_vol * multiplier
