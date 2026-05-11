"""
Trade Logger — SQLite + CSV persistence for backtesting review
"""
import csv
import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class TradeLogger:
    def __init__(self, db_path: str = 'trades.db'):
        self.db_path = db_path
        self.csv_path = db_path.replace('.db', '_trades.csv')
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT,
                    ticker      TEXT,
                    strategy    TEXT,
                    direction   TEXT,
                    entry       REAL,
                    stop_loss   REAL,
                    target      REAL,
                    shares      INTEGER,
                    dollar_risk REAL,
                    expiry      TEXT,
                    confidence  INTEGER,
                    rsi         REAL,
                    atr         REAL,
                    indicators  TEXT,
                    status      TEXT DEFAULT 'open',
                    exit_price  REAL,
                    pnl         REAL,
                    exit_time   TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS daily_summary (
                    date        TEXT PRIMARY KEY,
                    total_trades INTEGER,
                    wins        INTEGER,
                    losses      INTEGER,
                    gross_pnl   REAL,
                    win_rate    REAL
                )
            ''')
            conn.commit()
        logger.info(f"Trade DB initialized: {self.db_path}")

    def log_trade(self, signal: dict) -> int:
        """Insert a new trade entry (status=open)."""
        indicators_json = json.dumps(signal.get('indicators', {}))
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute('''
                INSERT INTO trades
                  (timestamp, ticker, strategy, direction, entry, stop_loss,
                   target, shares, dollar_risk, expiry, confidence, rsi, atr, indicators, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
            ''', (
                signal.get('timestamp', datetime.now().isoformat()),
                signal.get('ticker'),
                signal.get('strategy'),
                signal.get('direction'),
                signal.get('entry'),
                signal.get('stop_loss'),
                signal.get('target'),
                signal.get('shares', 0),
                signal.get('dollar_risk', 0),
                signal.get('expiry'),
                signal.get('confidence'),
                signal.get('rsi'),
                signal.get('atr'),
                indicators_json,
            ))
            trade_id = cur.lastrowid
            conn.commit()
        self._append_csv(signal)
        logger.info(f"Trade logged #{trade_id}: {signal.get('ticker')} {signal.get('direction')}")
        return trade_id

    def log_exit(self, position: dict, exit_price: float, pnl: float, trade_id: int = None):
        """Update trade record on close."""
        with sqlite3.connect(self.db_path) as conn:
            if trade_id:
                conn.execute('''
                    UPDATE trades
                    SET status='closed', exit_price=?, pnl=?, exit_time=?
                    WHERE id=?
                ''', (exit_price, pnl, datetime.now().isoformat(), trade_id))
            else:
                conn.execute('''
                    UPDATE trades
                    SET status='closed', exit_price=?, pnl=?, exit_time=?
                    WHERE ticker=? AND status='open'
                    ORDER BY id DESC LIMIT 1
                ''', (exit_price, pnl, datetime.now().isoformat(), position.get('ticker')))
            conn.commit()
        self._update_daily_summary()

    def _append_csv(self, signal: dict):
        file_exists = os.path.exists(self.csv_path)
        fields = [
            'timestamp', 'ticker', 'strategy', 'direction',
            'entry', 'stop_loss', 'target', 'shares',
            'dollar_risk', 'expiry', 'confidence', 'rsi', 'atr'
        ]
        with open(self.csv_path, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            if not file_exists:
                writer.writeheader()
            writer.writerow(signal)

    def _update_daily_summary(self):
        today = datetime.now().date().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute('''
                SELECT
                  COUNT(*) as total,
                  SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                  SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losses,
                  SUM(pnl) as gross_pnl
                FROM trades
                WHERE DATE(timestamp) = ? AND status = 'closed'
            ''', (today,)).fetchone()
            if row and row[0]:
                win_rate = (row[1] or 0) / row[0]
                conn.execute('''
                    INSERT INTO daily_summary (date, total_trades, wins, losses, gross_pnl, win_rate)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(date) DO UPDATE SET
                      total_trades=excluded.total_trades,
                      wins=excluded.wins,
                      losses=excluded.losses,
                      gross_pnl=excluded.gross_pnl,
                      win_rate=excluded.win_rate
                ''', (today, row[0], row[1] or 0, row[2] or 0, row[3] or 0, win_rate))
                conn.commit()

    def get_trades(self, limit: int = 100, status: str = None) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    'SELECT * FROM trades WHERE status=? ORDER BY id DESC LIMIT ?',
                    (status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM trades ORDER BY id DESC LIMIT ?', (limit,)
                ).fetchall()
        return [dict(r) for r in rows]

    def get_daily_summary(self, days: int = 30) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                'SELECT * FROM daily_summary ORDER BY date DESC LIMIT ?', (days,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_performance_stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            stats = conn.execute('''
                SELECT
                  COUNT(*) as total_trades,
                  SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                  SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losses,
                  SUM(pnl) as total_pnl,
                  AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_win,
                  AVG(CASE WHEN pnl <= 0 THEN pnl END) as avg_loss,
                  MAX(pnl) as best_trade,
                  MIN(pnl) as worst_trade
                FROM trades WHERE status = 'closed'
            ''').fetchone()
        if not stats or not stats[0]:
            return {}
        total = stats[0]
        wins = stats[1] or 0
        return {
            'total_trades': total,
            'wins': wins,
            'losses': stats[2] or 0,
            'win_rate': round(wins / total, 3) if total else 0,
            'total_pnl': round(stats[3] or 0, 2),
            'avg_win': round(stats[4] or 0, 2),
            'avg_loss': round(stats[5] or 0, 2),
            'best_trade': round(stats[6] or 0, 2),
            'worst_trade': round(stats[7] or 0, 2),
        }
