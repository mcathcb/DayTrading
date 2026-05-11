"""
Data Layer — Yahoo Finance OHLCV + Options Chain + Quote fetching
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class DataLayer:
    def __init__(self, config: dict):
        self.config = config
        self._cache: Dict[str, dict] = {}
        self._cache_ttl = 60  # seconds

    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache:
            return False
        age = (datetime.now() - self._cache[key]['ts']).total_seconds()
        return age < self._cache_ttl

    def get_ohlcv(self, ticker: str, period: str = '5d', interval: str = '5m') -> Optional[pd.DataFrame]:
        """Fetch OHLCV from Yahoo Finance with caching."""
        cache_key = f"{ticker}_{period}_{interval}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]['data']
        try:
            tkr = yf.Ticker(ticker)
            df = tkr.history(period=period, interval=interval, prepost=False)
            df.columns = [c.lower() for c in df.columns]
            df.index = pd.to_datetime(df.index)
            if df.empty:
                return None
            self._cache[cache_key] = {'data': df, 'ts': datetime.now()}
            return df
        except Exception as e:
            logger.error(f"OHLCV fetch error for {ticker}: {e}")
            return None

    def get_daily_ohlcv(self, ticker: str, lookback_days: int = 60) -> Optional[pd.DataFrame]:
        """Daily bars for resistance/support calculations."""
        try:
            tkr = yf.Ticker(ticker)
            df = tkr.history(period=f"{lookback_days}d", interval="1d")
            df.columns = [c.lower() for c in df.columns]
            return df if not df.empty else None
        except Exception as e:
            logger.error(f"Daily OHLCV error for {ticker}: {e}")
            return None

    def get_quote(self, ticker: str) -> Optional[dict]:
        """Real-time quote (last price, bid, ask)."""
        try:
            tkr = yf.Ticker(ticker)
            info = tkr.fast_info
            return {
                'ticker': ticker,
                'price': info.last_price,
                'volume': info.three_month_average_volume,
                'market_cap': info.market_cap,
            }
        except Exception as e:
            logger.error(f"Quote error for {ticker}: {e}")
            return None

    def get_options_chain(self, ticker: str, min_oi: int = 100) -> Optional[pd.DataFrame]:
        """
        Fetch full options chain — calls + puts with IV, Greeks, OI, volume.
        Returns unified DataFrame with 'type' column (call/put).
        """
        try:
            tkr = yf.Ticker(ticker)
            expirations = tkr.options
            if not expirations:
                return None

            # Grab next 3 expiries
            all_chains = []
            for exp in expirations[:3]:
                chain = tkr.option_chain(exp)
                calls = chain.calls.copy()
                puts = chain.puts.copy()
                calls['type'] = 'call'
                puts['type'] = 'put'
                calls['expiry'] = exp
                puts['expiry'] = exp
                all_chains.extend([calls, puts])

            df = pd.concat(all_chains, ignore_index=True)
            df.columns = [c.lower().replace(' ', '_') for c in df.columns]

            # Filter by min OI
            if 'openinterest' in df.columns:
                df = df[df['openinterest'] >= min_oi]

            return df
        except Exception as e:
            logger.error(f"Options chain error for {ticker}: {e}")
            return None

    def get_unusual_options_activity(self, ticker: str, vol_oi_ratio: float = 2.0) -> Optional[pd.DataFrame]:
        """
        Filter for unusual options: volume significantly exceeds open interest.
        High vol/OI ratio signals smart money positioning.
        """
        chain = self.get_options_chain(ticker)
        if chain is None:
            return None
        try:
            chain = chain.dropna(subset=['volume', 'openinterest', 'impliedvolatility'])
            chain = chain[chain['openinterest'] > 0]
            chain['vol_oi_ratio'] = chain['volume'] / chain['openinterest']
            unusual = chain[chain['vol_oi_ratio'] >= vol_oi_ratio].copy()
            return unusual.sort_values('vol_oi_ratio', ascending=False)
        except Exception as e:
            logger.error(f"Unusual options error for {ticker}: {e}")
            return None

    def has_upcoming_earnings(self, ticker: str, days: int = 1) -> bool:
        """Check if earnings are within `days` of today."""
        try:
            tkr = yf.Ticker(ticker)
            cal = tkr.calendar
            if cal is None or cal.empty:
                return False
            # calendar may have 'Earnings Date' as row index or column
            if 'Earnings Date' in cal.index:
                earn_date = cal.loc['Earnings Date'].iloc[0]
            elif 'Earnings Date' in cal.columns:
                earn_date = pd.to_datetime(cal['Earnings Date'].iloc[0])
            else:
                return False
            earn_date = pd.to_datetime(earn_date)
            delta = (earn_date.date() - datetime.now().date()).days
            return 0 <= delta <= days
        except Exception:
            return False

    def get_resistance_levels(self, ticker: str, window: int = 20) -> List[float]:
        """Simple swing-high resistance levels from daily data."""
        daily = self.get_daily_ohlcv(ticker, lookback_days=60)
        if daily is None or len(daily) < window:
            return []
        highs = daily['high'].rolling(window).max().dropna()
        # Return top 3 distinct resistance levels
        levels = sorted(set(highs.round(2)))[-3:]
        return levels
