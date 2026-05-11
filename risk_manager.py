"""
Risk Manager
- Kelly Criterion position sizing
- Fixed fractional fallback
- Max daily loss limit with auto-shutoff
- Per-trade risk capping
"""
import logging
import math
from typing import Dict

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self,
                 account_size: float = 25000,
                 max_risk_pct: float = 0.02,
                 max_daily_loss: float = 0.05,
                 sizing_method: str = 'fixed_fractional'):
        self.account_size = account_size
        self.max_risk_pct = max_risk_pct
        self.max_daily_loss = max_daily_loss
        self.sizing_method = sizing_method
        self.daily_realized_pnl = 0.0
        self.trade_log: list = []

    @property
    def daily_loss_limit(self) -> float:
        return self.account_size * self.max_daily_loss

    @property
    def max_risk_dollars(self) -> float:
        return self.account_size * self.max_risk_pct

    def size_position(self,
                      entry: float,
                      stop: float,
                      account: float = None,
                      win_rate: float = 0.55,
                      avg_win: float = 2.0,
                      avg_loss: float = 1.0) -> Dict:
        """
        Calculate position size using Kelly or Fixed Fractional.

        Args:
            entry:     Entry price per share
            stop:      Stop-loss price per share
            account:   Available account (uses self.account_size if None)
            win_rate:  Historical win rate (for Kelly, default 55%)
            avg_win:   Average win as multiple of risk
            avg_loss:  Average loss as multiple of risk (default 1.0)

        Returns:
            dict with shares, dollar_risk, position_value, method
        """
        account = account or self.account_size
        risk_per_share = abs(entry - stop)
        if risk_per_share <= 0:
            return {'shares': 0, 'dollar_risk': 0, 'position_value': 0, 'method': 'zero'}

        max_dollar_risk = min(account * self.max_risk_pct, self.max_risk_dollars)

        if self.sizing_method == 'kelly':
            shares = self._kelly(
                account, entry, stop, win_rate, avg_win, avg_loss, max_dollar_risk
            )
            method = 'kelly'
        else:
            shares = self._fixed_fractional(max_dollar_risk, risk_per_share)
            method = 'fixed_fractional'

        shares = max(1, int(shares))
        actual_risk = shares * risk_per_share
        position_value = shares * entry

        # Safety cap: don't risk more than max
        if actual_risk > max_dollar_risk * 1.1:
            shares = max(1, int(max_dollar_risk / risk_per_share))
            actual_risk = shares * risk_per_share
            position_value = shares * entry

        logger.info(
            f"Position sized: {shares} shares | "
            f"Risk: ${actual_risk:.2f} | "
            f"Value: ${position_value:.2f} | "
            f"Method: {method}"
        )
        return {
            'shares': shares,
            'dollar_risk': round(actual_risk, 2),
            'position_value': round(position_value, 2),
            'risk_per_share': round(risk_per_share, 4),
            'method': method,
        }

    def _kelly(self,
               account: float,
               entry: float,
               stop: float,
               win_rate: float,
               avg_win: float,
               avg_loss: float,
               max_dollar_risk: float) -> int:
        """
        Kelly Criterion: f* = (bp - q) / b
          b = reward/risk ratio (avg_win / avg_loss)
          p = win probability
          q = 1 - p
        Half-Kelly applied for safety.
        """
        b = avg_win / avg_loss if avg_loss > 0 else 2.0
        p = win_rate
        q = 1 - p
        kelly_f = (b * p - q) / b
        half_kelly = max(0, kelly_f / 2)  # Half-Kelly
        kelly_f = min(half_kelly, self.max_risk_pct)  # Cap at max risk
        dollar_allocation = account * kelly_f
        risk_per_share = abs(entry - stop)
        return int(min(dollar_allocation, max_dollar_risk) / risk_per_share) if risk_per_share > 0 else 0

    def _fixed_fractional(self, max_dollar_risk: float, risk_per_share: float) -> int:
        """Fixed % of account at risk, divided by risk per share."""
        return int(max_dollar_risk / risk_per_share)

    def check_daily_limit(self, current_loss: float) -> bool:
        """Returns True if daily loss limit is exceeded."""
        return current_loss >= self.daily_loss_limit

    def record_trade(self, pnl: float):
        self.daily_realized_pnl += pnl
        self.trade_log.append(pnl)

    def reset_daily(self):
        """Call at market open each day."""
        self.daily_realized_pnl = 0.0
        logger.info("Daily P&L reset.")

    def get_stats(self) -> dict:
        trades = self.trade_log
        if not trades:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'expectancy': 0,
                'kelly_f': 0,
            }
        wins = [t for t in trades if t > 0]
        losses = [t for t in trades if t <= 0]
        win_rate = len(wins) / len(trades)
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 1
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        b = avg_win / avg_loss if avg_loss > 0 else 2.0
        kelly = max(0, (b * win_rate - (1 - win_rate)) / b)
        return {
            'total_trades': len(trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': round(win_rate, 3),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'expectancy': round(expectancy, 2),
            'kelly_f': round(kelly, 4),
            'daily_pnl': round(self.daily_realized_pnl, 2),
        }
