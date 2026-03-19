"""Persistent SQLite-backed research memory for autoresearch.

Stores experiment results, auto-generates insights, and maintains
research priorities across overnight runs. Each night gets smarter.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Any

from pyhood.autoresearch.models import ExperimentResult


class ResearchMemory:
    """Persistent SQLite-backed research memory for autoresearch.

    Stores experiment results, auto-generates insights, and maintains
    research priorities across overnight runs. Each night gets smarter.
    """

    def __init__(self, db_path: str = 'autoresearch_memory.db'):
        """Initialize or connect to existing database."""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self) -> None:
        """Create all tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                run_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                params_json TEXT NOT NULL,
                train_sharpe REAL,
                train_return REAL,
                train_trades INTEGER,
                train_max_drawdown REAL,
                train_win_rate REAL,
                train_profit_factor REAL,
                test_sharpe REAL,
                test_return REAL,
                test_trades INTEGER,
                test_max_drawdown REAL,
                test_win_rate REAL,
                test_profit_factor REAL,
                validate_sharpe REAL,
                validate_return REAL,
                validate_trades INTEGER,
                regime_breakdown_json TEXT,
                cross_validation_json TEXT,
                kept INTEGER NOT NULL DEFAULT 0,
                reason TEXT,
                overfit_flagged INTEGER NOT NULL DEFAULT 0,
                overfit_gap REAL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_date TEXT NOT NULL DEFAULT (datetime('now')),
                category TEXT NOT NULL,
                insight_text TEXT NOT NULL,
                confidence TEXT NOT NULL,
                evidence_count INTEGER NOT NULL DEFAULT 0,
                source_experiment_ids TEXT,
                still_valid INTEGER NOT NULL DEFAULT 1,
                invalidated_date TEXT,
                invalidated_reason TEXT
            );

            CREATE TABLE IF NOT EXISTS priorities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_date TEXT NOT NULL DEFAULT (datetime('now')),
                description TEXT NOT NULL,
                priority_level TEXT NOT NULL,
                strategy_name TEXT,
                ticker TEXT,
                params_json TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                completed_date TEXT,
                source_insight_id INTEGER,
                result_experiment_id INTEGER,
                FOREIGN KEY (source_insight_id) REFERENCES insights(id)
            );

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                end_time TEXT,
                ticker TEXT NOT NULL,
                total_experiments INTEGER NOT NULL DEFAULT 0,
                kept_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0,
                best_strategy TEXT,
                best_sharpe REAL,
                new_insights_generated INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'running'
            );
        """)
        self.conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()

    # ================================================================
    # Experiment Storage
    # ================================================================

    def store_experiment(self, experiment: ExperimentResult, run_id: int, ticker: str) -> int:
        """Store a single experiment result. Returns the experiment ID."""
        train = experiment.train_result
        test = experiment.test_result
        validate = experiment.validate_result

        # Calculate overfit gap
        overfit_flagged = 0
        overfit_gap = None
        if test is not None and train.sharpe_ratio != 0:
            overfit_gap = abs(train.sharpe_ratio - test.sharpe_ratio) / abs(train.sharpe_ratio)
            if overfit_gap > 0.50:
                overfit_flagged = 1

        # Extract regime breakdown
        regime_json = None
        if train.regime_breakdown:
            regime_json = json.dumps(train.regime_breakdown)

        # Extract cross-validation
        cv_json = None
        if experiment.cross_validation:
            cv_json = json.dumps(experiment.cross_validation)

        # Handle profit_factor inf
        def _safe_pf(pf: float) -> float | None:
            if pf is None:
                return None
            if pf == float('inf'):
                return 999999.0
            return pf

        cursor = self.conn.execute(
            """INSERT INTO experiments (
                run_id, run_date, ticker, strategy_name, params_json,
                train_sharpe, train_return, train_trades,
                train_max_drawdown, train_win_rate, train_profit_factor,
                test_sharpe, test_return, test_trades,
                test_max_drawdown, test_win_rate, test_profit_factor,
                validate_sharpe, validate_return, validate_trades,
                regime_breakdown_json, cross_validation_json,
                kept, reason, overfit_flagged, overfit_gap
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            (
                run_id,
                datetime.now().isoformat(),
                ticker,
                experiment.strategy_name,
                json.dumps(experiment.params, sort_keys=True),
                train.sharpe_ratio,
                train.total_return,
                train.total_trades,
                train.max_drawdown,
                train.win_rate,
                _safe_pf(train.profit_factor),
                test.sharpe_ratio if test else None,
                test.total_return if test else None,
                test.total_trades if test else None,
                test.max_drawdown if test else None,
                test.win_rate if test else None,
                _safe_pf(test.profit_factor) if test else None,
                validate.sharpe_ratio if validate else None,
                validate.total_return if validate else None,
                validate.total_trades if validate else None,
                regime_json,
                cv_json,
                1 if experiment.kept else 0,
                experiment.reason,
                overfit_flagged,
                overfit_gap,
            )
        )
        self.conn.commit()
        return cursor.lastrowid

    def store_experiments(
        self, experiments: list[ExperimentResult], run_id: int, ticker: str,
    ) -> list[int]:
        """Store multiple experiment results."""
        return [self.store_experiment(exp, run_id, ticker) for exp in experiments]

    def get_experiments(
        self,
        ticker: str = None,
        strategy_name: str = None,
        min_test_sharpe: float = None,
        kept_only: bool = False,
        limit: int = 100,
    ) -> list[dict]:
        """Query experiments with filters."""
        conditions = []
        params = []

        if ticker is not None:
            conditions.append("ticker = ?")
            params.append(ticker)
        if strategy_name is not None:
            conditions.append("strategy_name LIKE ?")
            params.append(f"%{strategy_name}%")
        if min_test_sharpe is not None:
            conditions.append("test_sharpe >= ?")
            params.append(min_test_sharpe)
        if kept_only:
            conditions.append("kept = 1")

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        rows = self.conn.execute(
            f"SELECT * FROM experiments {where} ORDER BY id DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(row) for row in rows]

    def experiment_exists(self, ticker: str, strategy_name: str, params: dict) -> bool:
        """Check if this exact experiment has already been run. For resume/skip."""
        params_json = json.dumps(params, sort_keys=True)
        row = self.conn.execute(
            "SELECT COUNT(*) FROM experiments"
            " WHERE ticker = ? AND strategy_name = ? AND params_json = ?",
            (ticker, strategy_name, params_json),
        ).fetchone()
        return row[0] > 0

    # ================================================================
    # Run Tracking
    # ================================================================

    def start_run(self, ticker: str) -> int:
        """Record a new run starting. Returns run_id."""
        cursor = self.conn.execute(
            "INSERT INTO runs (start_time, ticker, status) VALUES (?, ?, 'running')",
            (datetime.now().isoformat(), ticker),
        )
        self.conn.commit()
        return cursor.lastrowid

    def end_run(self, run_id: int, status: str = 'completed') -> None:
        """Record run completion with final stats."""
        # Gather stats from experiments
        row = self.conn.execute(
            """SELECT
                COUNT(*) as total,
                SUM(CASE WHEN kept = 1 THEN 1 ELSE 0 END) as kept_count,
                MAX(CASE WHEN test_sharpe IS NOT NULL THEN test_sharpe ELSE NULL END) as best_sharpe
            FROM experiments WHERE run_id = ?""",
            (run_id,),
        ).fetchone()

        # Get best strategy name
        best_row = self.conn.execute(
            """SELECT strategy_name FROM experiments
            WHERE run_id = ? AND test_sharpe IS NOT NULL
            ORDER BY test_sharpe DESC LIMIT 1""",
            (run_id,),
        ).fetchone()

        # Count insights generated for this run
        insight_count = self.conn.execute(
            """SELECT COUNT(*) FROM insights
            WHERE source_experiment_ids LIKE ?""",
            (f'%"run_id": {run_id}%',),
        ).fetchone()[0]

        self.conn.execute(
            """UPDATE runs SET
                end_time = ?,
                total_experiments = ?,
                kept_count = ?,
                best_strategy = ?,
                best_sharpe = ?,
                new_insights_generated = ?,
                status = ?
            WHERE id = ?""",
            (
                datetime.now().isoformat(),
                row['total'] or 0 if row else 0,
                row['kept_count'] or 0 if row else 0,
                best_row['strategy_name'] if best_row else None,
                row['best_sharpe'] if row else None,
                insight_count,
                status,
                run_id,
            ),
        )
        self.conn.commit()

    def get_runs(self, limit: int = 20) -> list[dict]:
        """Get recent run history."""
        rows = self.conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    # ================================================================
    # Insight Generation
    # ================================================================

    def generate_insights(self, run_id: int = None) -> list[dict]:
        """Auto-generate insights from experiment data."""
        new_insights: list[dict] = []

        # Get relevant experiments
        if run_id is not None:
            rows = self.conn.execute(
                "SELECT * FROM experiments WHERE run_id = ?", (run_id,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM experiments").fetchall()

        experiments = [dict(r) for r in rows]
        if not experiments:
            return new_insights

        # 1. Strategy Performance Insights
        new_insights.extend(self._detect_strategy_performance(experiments))

        # 2. Overfitting Detection
        new_insights.extend(self._detect_overfitting(experiments))

        # 3. Regime Insights
        new_insights.extend(self._detect_regime_patterns(experiments))

        # 4. Parameter Insights
        new_insights.extend(self._detect_parameter_patterns(experiments))

        # 5. Ticker Insights
        new_insights.extend(self._detect_ticker_patterns(experiments))

        return new_insights

    def _insight_already_exists(self, category: str, text: str) -> bool:
        """Check if a similar insight already exists and is valid."""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM insights"
            " WHERE category = ? AND insight_text = ? AND still_valid = 1",
            (category, text),
        ).fetchone()
        return row[0] > 0

    def _store_insight(self, category: str, text: str, confidence: str,
                       evidence_count: int, source_ids: list[int]) -> dict | None:
        """Store an insight if it doesn't already exist."""
        if self._insight_already_exists(category, text):
            return None

        cursor = self.conn.execute(
            """INSERT INTO insights (
                category, insight_text, confidence,
                evidence_count, source_experiment_ids)
            VALUES (?, ?, ?, ?, ?)""",
            (category, text, confidence, evidence_count, json.dumps(source_ids)),
        )
        self.conn.commit()
        insight = {
            'id': cursor.lastrowid,
            'category': category,
            'insight_text': text,
            'confidence': confidence,
            'evidence_count': evidence_count,
        }
        return insight

    def _detect_strategy_performance(self, experiments: list[dict]) -> list[dict]:
        """Detect strategy performance patterns."""
        new_insights = []

        # Group by base strategy name (strip params from name)
        strategy_ticker_data: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for exp in experiments:
            # Extract base strategy name (before the parenthesized params)
            name = exp['strategy_name']
            base_name = name.split('(')[0].strip() if '(' in name else name
            ticker = exp['ticker']
            strategy_ticker_data[base_name][ticker].append(exp)

        for strategy, ticker_data in strategy_ticker_data.items():
            # Check for strategy failing across tickers
            failing_tickers = []
            all_exp_ids = []
            for ticker, exps in ticker_data.items():
                test_sharpes = [e['test_sharpe'] for e in exps if e['test_sharpe'] is not None]
                if test_sharpes and sum(test_sharpes) / len(test_sharpes) < 0.3:
                    failing_tickers.append(ticker)
                all_exp_ids.extend([e['id'] for e in exps])

            if len(failing_tickers) >= 3:
                count = sum(len(ticker_data[t]) for t in failing_tickers)
                confidence = 'high' if count >= 5 else 'medium'
                text = f"{strategy} consistently fails across tickers: {', '.join(failing_tickers)}"
                insight = self._store_insight(
                    'strategy_performance', text, confidence, count, all_exp_ids,
                )
                if insight:
                    new_insights.append(insight)

            # Check for strategy showing promise on specific ticker
            for ticker, exps in ticker_data.items():
                test_sharpes = [e['test_sharpe'] for e in exps if e['test_sharpe'] is not None]
                if not test_sharpes:
                    continue
                best_sharpe = max(test_sharpes)
                if best_sharpe > 0.7:
                    exp_ids = [e['id'] for e in exps]
                    # Check for validation and cross-validation
                    has_validate = any(e['validate_sharpe'] is not None for e in exps)
                    has_cv = any(e['cross_validation_json'] is not None for e in exps)
                    confidence = 'high' if (has_validate and has_cv) else 'medium'
                    text = (
                        f"{strategy} shows promise on {ticker}"
                        f" (best test Sharpe: {best_sharpe:.2f})"
                    )
                    insight = self._store_insight(
                        'strategy_performance', text, confidence,
                        len(exps), exp_ids,
                    )
                    if insight:
                        new_insights.append(insight)

        return new_insights

    def _detect_overfitting(self, experiments: list[dict]) -> list[dict]:
        """Detect overfitting patterns."""
        new_insights = []

        # Individual overfit detection (train/test gap > 50%)
        for exp in experiments:
            if (exp['overfit_flagged']
                    and exp['overfit_gap'] is not None
                    and exp['overfit_gap'] > 0.5):
                params = exp['params_json']
                gap = exp['overfit_gap']
                text = (
                    f"{exp['strategy_name']} with params {params}"
                    f" is likely overfitted (gap: {gap:.0%})"
                )
                insight = self._store_insight('overfitting', text, 'high', 1, [exp['id']])
                if insight:
                    new_insights.append(insight)

        # Strategy family overfitting on a ticker
        strategy_ticker_data: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for exp in experiments:
            name = exp['strategy_name']
            base_name = name.split('(')[0].strip() if '(' in name else name
            strategy_ticker_data[base_name][exp['ticker']].append(exp)

        for strategy, ticker_data in strategy_ticker_data.items():
            for ticker, exps in ticker_data.items():
                if len(exps) < 3:
                    continue
                overfit_count = sum(1 for e in exps if e['overfit_flagged'])
                ratio = overfit_count / len(exps)
                if ratio > 0.6:
                    exp_ids = [e['id'] for e in exps]
                    confidence = 'high' if len(exps) >= 5 else 'medium'
                    text = (
                        f"{strategy} family tends to overfit on {ticker}"
                        f" ({overfit_count}/{len(exps)} overfitted)"
                    )
                    insight = self._store_insight(
                        'overfitting', text, confidence, len(exps), exp_ids,
                    )
                    if insight:
                        new_insights.append(insight)

        return new_insights

    def _detect_regime_patterns(self, experiments: list[dict]) -> list[dict]:
        """Detect regime-dependent patterns."""
        new_insights = []

        for exp in experiments:
            if not exp['regime_breakdown_json']:
                continue

            try:
                breakdown = json.loads(exp['regime_breakdown_json'])
            except (json.JSONDecodeError, TypeError):
                continue

            if not breakdown:
                continue

            # Calculate P&L by regime
            regime_pnl = {}
            total_pnl = 0
            for regime, data in breakdown.items():
                pnl = data.get('total_pnl', 0) if isinstance(data, dict) else 0
                regime_pnl[regime] = pnl
                total_pnl += abs(pnl)

            if total_pnl == 0:
                continue

            # Check if 80%+ of P&L from one regime
            profitable_regimes = 0
            for regime, pnl in regime_pnl.items():
                if abs(pnl) / total_pnl > 0.8:
                    name = exp['strategy_name']
                    base_name = name.split('(')[0].strip() if '(' in name else name
                    text = f"{base_name} is regime-dependent (dominated by {regime} regime)"
                    insight = self._store_insight('regime', text, 'high', 1, [exp['id']])
                    if insight:
                        new_insights.append(insight)
                    break
                if pnl > 0:
                    profitable_regimes += 1

            # Check if profitable across 3+ regimes
            if profitable_regimes >= 3:
                name = exp['strategy_name']
                base_name = name.split('(')[0].strip() if '(' in name else name
                text = f"{base_name} performs well across {profitable_regimes} regimes"
                insight = self._store_insight('regime', text, 'medium', 1, [exp['id']])
                if insight:
                    new_insights.append(insight)

        return new_insights

    def _detect_parameter_patterns(self, experiments: list[dict]) -> list[dict]:
        """Detect parameter optimization patterns."""
        new_insights = []

        # Group by strategy+ticker
        groups: dict[tuple[str, str], list] = defaultdict(list)
        for exp in experiments:
            if exp['test_sharpe'] is None:
                continue
            name = exp['strategy_name']
            base_name = name.split('(')[0].strip() if '(' in name else name
            groups[(base_name, exp['ticker'])].append(exp)

        for (strategy, ticker), exps in groups.items():
            if len(exps) < 3:
                continue

            # Sort by test sharpe to find top performers
            sorted_exps = sorted(exps, key=lambda e: e['test_sharpe'] or 0, reverse=True)
            top3 = sorted_exps[:3]

            # Check each parameter for convergence
            try:
                params_list = [json.loads(e['params_json']) for e in top3]
            except (json.JSONDecodeError, TypeError):
                continue

            if not params_list:
                continue

            all_keys = set()
            for p in params_list:
                all_keys.update(p.keys())

            for key in all_keys:
                values = [p.get(key) for p in params_list if key in p]
                if not values or not all(isinstance(v, (int, float)) for v in values):
                    continue

                # Check if top 3 have similar values (within 30% of mean)
                mean_val = sum(values) / len(values)
                if mean_val == 0:
                    continue
                spread = max(abs(v - mean_val) / abs(mean_val) for v in values)
                if spread < 0.3 and len(values) >= 3:
                    text = f"For {strategy} on {ticker}, optimal {key} is around {mean_val:.1f}"
                    exp_ids = [e['id'] for e in top3]
                    insight = self._store_insight('parameter', text, 'medium', len(exps), exp_ids)
                    if insight:
                        new_insights.append(insight)

        return new_insights

    def _detect_ticker_patterns(self, experiments: list[dict]) -> list[dict]:
        """Detect ticker-level patterns."""
        new_insights = []

        # Group by ticker
        ticker_data: dict[str, list] = defaultdict(list)
        for exp in experiments:
            if exp['test_sharpe'] is None:
                continue
            ticker_data[exp['ticker']].append(exp)

        # Define trend-following strategy families
        trend_strategies = {'EMA', 'MACD', 'Golden Cross', 'Donchian', 'Keltner'}

        for ticker, exps in ticker_data.items():
            # Check for trend-following success
            trend_successes = 0
            exp_ids = []
            for exp in exps:
                name = exp['strategy_name']
                base_name = name.split('(')[0].strip() if '(' in name else name
                if any(ts in base_name for ts in trend_strategies):
                    if exp['test_sharpe'] is not None and exp['test_sharpe'] > 0.7:
                        trend_successes += 1
                        exp_ids.append(exp['id'])

            if trend_successes >= 2:
                text = (
                    f"{ticker} responds well to trend-following strategies"
                    f" ({trend_successes} strategies with Sharpe > 0.7)"
                )
                insight = self._store_insight('ticker', text, 'medium', trend_successes, exp_ids)
                if insight:
                    new_insights.append(insight)

        return new_insights

    def get_insights(self, category: str = None, confidence: str = None,
                     valid_only: bool = True) -> list[dict]:
        """Query insights with filters."""
        conditions = []
        params = []

        if category is not None:
            conditions.append("category = ?")
            params.append(category)
        if confidence is not None:
            conditions.append("confidence = ?")
            params.append(confidence)
        if valid_only:
            conditions.append("still_valid = 1")

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        rows = self.conn.execute(
            f"SELECT * FROM insights {where} ORDER BY id DESC",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def invalidate_insight(self, insight_id: int, reason: str) -> None:
        """Mark an insight as no longer valid."""
        self.conn.execute(
            """UPDATE insights SET still_valid = 0, invalidated_date = ?, invalidated_reason = ?
            WHERE id = ?""",
            (datetime.now().isoformat(), reason, insight_id),
        )
        self.conn.commit()

    # ================================================================
    # Priority Management
    # ================================================================

    def generate_priorities(self, run_id: int = None) -> list[dict]:
        """Auto-generate research priorities from insights."""
        new_priorities: list[dict] = []

        insights = self.get_insights(valid_only=True)
        if not insights:
            return new_priorities

        for insight in insights:
            category = insight['category']
            text = insight['insight_text']
            insight_id = insight['id']

            if category == 'strategy_performance' and 'shows promise' in text:
                # Extract strategy and ticker from insight text
                priority = self._create_priority(
                    description=f"Explore nearby params for promising result: {text}",
                    priority_level='high',
                    source_insight_id=insight_id,
                )
                if priority:
                    new_priorities.append(priority)

            elif category == 'strategy_performance' and 'fails' in text:
                priority = self._create_priority(
                    description=f"Confirm failure with extreme params: {text}",
                    priority_level='low',
                    source_insight_id=insight_id,
                )
                if priority:
                    new_priorities.append(priority)

            elif category == 'overfitting' and 'family tends to overfit' in text:
                priority = self._create_priority(
                    description=f"Investigate overfitting pattern: {text}",
                    priority_level='medium',
                    source_insight_id=insight_id,
                )
                if priority:
                    new_priorities.append(priority)

            elif category == 'regime' and 'regime-dependent' in text:
                priority = self._create_priority(
                    description=f"Test regime-specific variations: {text}",
                    priority_level='medium',
                    source_insight_id=insight_id,
                )
                if priority:
                    new_priorities.append(priority)

            elif category == 'ticker' and 'responds well' in text:
                priority = self._create_priority(
                    description=f"Expand strategy testing: {text}",
                    priority_level='medium',
                    source_insight_id=insight_id,
                )
                if priority:
                    new_priorities.append(priority)

        return new_priorities

    def _create_priority(self, description: str, priority_level: str,
                         source_insight_id: int = None,
                         strategy_name: str = None, ticker: str = None,
                         params: dict = None) -> dict | None:
        """Create a priority if a similar one doesn't already exist."""
        # Check for duplicate
        existing = self.conn.execute(
            "SELECT COUNT(*) FROM priorities WHERE description = ? AND status = 'pending'",
            (description,),
        ).fetchone()
        if existing[0] > 0:
            return None

        params_json = json.dumps(params, sort_keys=True) if params else None
        cursor = self.conn.execute(
            """INSERT INTO priorities (
                description, priority_level, strategy_name,
                ticker, params_json, source_insight_id
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (description, priority_level, strategy_name, ticker, params_json, source_insight_id),
        )
        self.conn.commit()
        return {
            'id': cursor.lastrowid,
            'description': description,
            'priority_level': priority_level,
            'status': 'pending',
            'source_insight_id': source_insight_id,
        }

    def get_priorities(self, status: str = 'pending', priority_level: str = None) -> list[dict]:
        """Get priorities, default pending only."""
        conditions = ["status = ?"]
        params: list[Any] = [status]

        if priority_level is not None:
            conditions.append("priority_level = ?")
            params.append(priority_level)

        where = "WHERE " + " AND ".join(conditions)
        rows = self.conn.execute(
            f"SELECT * FROM priorities {where} ORDER BY "
            "CASE priority_level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def update_priority(
        self, priority_id: int, status: str, result_experiment_id: int = None,
    ) -> None:
        """Update priority status."""
        completed_date = datetime.now().isoformat() if status == 'completed' else None
        self.conn.execute(
            """UPDATE priorities SET status = ?, completed_date = ?, result_experiment_id = ?
            WHERE id = ?""",
            (status, completed_date, result_experiment_id, priority_id),
        )
        self.conn.commit()

    # ================================================================
    # Intelligence for Overnight Runner
    # ================================================================

    def should_skip(self, ticker: str, strategy_name: str, params: dict) -> tuple[bool, str]:
        """Check if this experiment should be skipped based on insights.

        Returns (should_skip: bool, reason: str)
        """
        # 1. Check if exact experiment already run (dedupe)
        if self.experiment_exists(ticker, strategy_name, params):
            return True, "Already run (dedupe)"

        # 2. Check high-confidence insights about strategy failure
        base_name = (
            strategy_name.split('(')[0].strip()
            if '(' in strategy_name else strategy_name
        )
        insights = self.get_insights(
            category='strategy_performance', confidence='high', valid_only=True,
        )
        for insight in insights:
            if base_name in insight['insight_text'] and 'fails' in insight['insight_text']:
                if ticker in insight['insight_text']:
                    return True, f"High-confidence insight: {insight['insight_text']}"

        # 3. Check if strategy/params overfitted
        params_json = json.dumps(params, sort_keys=True)
        overfit_insights = self.get_insights(category='overfitting', valid_only=True)
        for insight in overfit_insights:
            if params_json in insight['insight_text'] and strategy_name in insight['insight_text']:
                return True, f"Overfitting insight: {insight['insight_text']}"

        return False, ""

    def get_suggested_experiments(self, ticker: str, limit: int = 20) -> list[dict]:
        """Get prioritized experiments to run next.

        Returns list of {strategy_name, params, reason, priority_level}
        Ordered by priority level (high first).
        """
        priorities = self.get_priorities(status='pending')

        suggestions = []
        for p in priorities:
            if p['ticker'] and p['ticker'] != ticker:
                continue
            suggestion = {
                'strategy_name': p['strategy_name'],
                'params': json.loads(p['params_json']) if p['params_json'] else {},
                'reason': p['description'],
                'priority_level': p['priority_level'],
                'priority_id': p['id'],
            }
            suggestions.append(suggestion)
            if len(suggestions) >= limit:
                break

        return suggestions

    def get_run_summary(self, run_id: int = None) -> str:
        """Human-readable summary of a run or all runs."""
        if run_id is not None:
            run_row = self.conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if not run_row:
                return f"No run found with id {run_id}"
            run = dict(run_row)
            lines = [
                f"=== Run #{run['id']} Summary ===",
                f"Ticker: {run['ticker']}",
                f"Status: {run['status']}",
                f"Started: {run['start_time']}",
                f"Ended: {run['end_time'] or 'still running'}",
                f"Total experiments: {run['total_experiments']}",
                f"Kept: {run['kept_count']}",
                f"Errors: {run['error_count']}",
                f"Best strategy: {run['best_strategy'] or 'N/A'}",
                (f"Best Sharpe: {run['best_sharpe']:.4f}"
                 if run['best_sharpe'] else "Best Sharpe: N/A"),
                f"New insights: {run['new_insights_generated']}",
            ]
            return "\n".join(lines)
        else:
            # Summary of all runs
            runs = self.get_runs()
            if not runs:
                return "No runs recorded yet."

            stats = self.stats()
            lines = [
                "=== Research Memory Summary ===",
                f"Total runs: {stats['total_runs']}",
                f"Total experiments: {stats['total_experiments']}",
                f"Total insights: {stats['total_insights']}",
                f"Active insights: {stats['active_insights']}",
                f"Pending priorities: {stats['pending_priorities']}",
                "",
                "Recent runs:",
            ]
            for run in runs[:5]:
                lines.append(
                    f"  #{run['id']} {run['ticker']} - {run['status']} "
                    f"({run['total_experiments']} experiments, {run['kept_count']} kept)"
                )
            return "\n".join(lines)

    # ================================================================
    # Stats
    # ================================================================

    def stats(self) -> dict:
        """Return overall stats: total experiments, insights, runs, etc."""
        total_experiments = self.conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
        total_insights = self.conn.execute("SELECT COUNT(*) FROM insights").fetchone()[0]
        active_insights = self.conn.execute(
            "SELECT COUNT(*) FROM insights WHERE still_valid = 1"
        ).fetchone()[0]
        total_runs = self.conn.execute(
            "SELECT COUNT(*) FROM runs"
        ).fetchone()[0]
        pending_priorities = self.conn.execute(
            "SELECT COUNT(*) FROM priorities WHERE status = 'pending'"
        ).fetchone()[0]
        kept_experiments = self.conn.execute(
            "SELECT COUNT(*) FROM experiments WHERE kept = 1"
        ).fetchone()[0]
        overfit_flagged = self.conn.execute(
            "SELECT COUNT(*) FROM experiments WHERE overfit_flagged = 1"
        ).fetchone()[0]

        return {
            'total_experiments': total_experiments,
            'total_insights': total_insights,
            'active_insights': active_insights,
            'total_runs': total_runs,
            'pending_priorities': pending_priorities,
            'kept_experiments': kept_experiments,
            'overfit_flagged': overfit_flagged,
        }
