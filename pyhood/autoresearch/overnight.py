"""OvernightRunner — resilient overnight execution engine for autoresearch.

Runs the full strategy parameter sweep program with:
- Resume from log (skip already-completed experiments)
- Try/catch per experiment (never let one bad experiment kill the run)
- Per-experiment timeout (threading-based, cross-platform)
- Save after every experiment (lose at most 1 on crash)
- Structured results directory with human-readable summaries
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import threading
import traceback
from datetime import datetime

from pyhood.autoresearch.audit import AuditTrail
from pyhood.autoresearch.memory import ResearchMemory
from pyhood.autoresearch.runner import AutoResearcher
from pyhood.backtest.strategies import (
    bollinger_breakout,
    bull_flag_breakout,
    donchian_breakout,
    ema_crossover,
    golden_cross,
    keltner_squeeze,
    ma_atr_mean_reversion,
    macd_crossover,
    rsi2_connors,
    rsi_mean_reversion,
    volume_confirmed_breakout,
)


class _ExperimentTimeoutError(Exception):
    pass


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Strategy sweep definitions
# ---------------------------------------------------------------------------

STRATEGY_SWEEPS: list[dict] = [
    {
        'name': 'EMA Crossover',
        'factory': ema_crossover,
        'grid': {
            'fast': [5, 7, 9, 11, 13, 15, 20],
            'slow': [15, 20, 25, 30, 40, 50, 100],
        },
    },
    {
        'name': 'MACD',
        'factory': macd_crossover,
        'grid': {
            'fast': [8, 10, 12, 14, 16],
            'slow': [20, 24, 26, 30, 35],
            'signal': [5, 7, 9, 11, 13],
        },
    },
    {
        'name': 'RSI Mean Reversion',
        'factory': rsi_mean_reversion,
        'grid': {
            'period': [7, 10, 14, 20],
            'oversold': [15, 20, 25, 30, 35],
            'overbought': [65, 70, 75, 80, 85],
        },
    },
    {
        'name': 'RSI(2) Connors',
        'factory': rsi2_connors,
        'grid': {
            'rsi_period': [2, 3, 4],
            'sma_period': [100, 150, 200],
            'oversold': [5, 10, 15, 20],
            'overbought': [80, 85, 90, 95],
        },
    },
    {
        'name': 'Bollinger Breakout',
        'factory': bollinger_breakout,
        'grid': {
            'period': [10, 15, 20, 25, 30],
            'std_dev': [1.5, 2.0, 2.5, 3.0],
        },
    },
    {
        'name': 'Donchian Breakout',
        'factory': donchian_breakout,
        'grid': {
            'entry_period': [10, 15, 20, 25, 30, 40],
            'exit_period': [5, 7, 10, 15, 20],
        },
    },
    {
        'name': 'MA+ATR Mean Reversion',
        'factory': ma_atr_mean_reversion,
        'grid': {
            'ma_period': [20, 30, 40, 50, 60],
            'entry_multiplier': [0.5, 0.75, 1.0, 1.25, 1.5],
            'exit_multiplier': [0.25, 0.5, 0.75, 1.0],
        },
    },
    {
        'name': 'Golden Cross',
        'factory': golden_cross,
        'grid': {
            'fast_period': [20, 30, 50, 75],
            'slow_period': [100, 150, 200, 250],
        },
    },
    {
        'name': 'Keltner Squeeze',
        'factory': keltner_squeeze,
        'grid': {
            'keltner_period': [10, 15, 20, 25],
            'keltner_atr_mult': [1.0, 1.5, 2.0, 2.5],
        },
    },
    {
        'name': 'Volume Confirmed',
        'factory': volume_confirmed_breakout,
        'grid': {
            'sma_period': [20, 30, 50, 75],
            'threshold': [0.5, 0.6, 0.7, 0.8],
        },
    },
    {
        'name': 'Bull Flag',
        'factory': bull_flag_breakout,
        'grid': {
            'pole_min_pct': [3, 5, 7, 10],
            'flag_max_bars': [7, 10, 15, 20],
        },
    },
]


def _count_combos(grid: dict[str, list]) -> int:
    """Count total parameter combinations in a grid."""
    total = 1
    for values in grid.values():
        total *= len(values)
    return total


def _grid_combos(grid: dict[str, list]) -> list[dict]:
    """Expand a parameter grid into a list of param dicts."""
    keys = list(grid.keys())
    value_lists = [grid[k] for k in keys]
    return [dict(zip(keys, combo)) for combo in itertools.product(*value_lists)]


class _ExperimentTimeoutErrorError(Exception):
    """Raised when an experiment exceeds its timeout."""


class OvernightRunner:
    """Resilient overnight execution engine for autoresearch.

    Features:
    - Resume from previous run (auto-detects experiments.json)
    - Per-experiment try/catch (one failure never kills the run)
    - Per-experiment timeout via threading
    - Saves after every experiment for crash safety
    - Structured results directory with logs and summaries
    """

    def __init__(
        self,
        ticker: str = 'SPY',
        total_period: str = '10y',
        results_dir: str = 'autoresearch_results',
        experiment_timeout: int = 60,
        save_every: int = 1,
        slippage_pct: float = 0.01,
        notify_telegram: bool = False,
        candles=None,
        cross_validate_tickers: list[str] | None = None,
        strategy_sweeps: list[dict] | None = None,
        memory_db: str = 'autoresearch_memory.db',
        audit: bool = True,
    ):
        self.ticker = ticker
        self.total_period = total_period
        self.results_dir = results_dir
        self.experiment_timeout = experiment_timeout
        self.save_every = save_every
        self.slippage_pct = slippage_pct
        self.notify_telegram = notify_telegram
        self._candles = candles
        self._cross_validate_tickers = cross_validate_tickers
        self.strategy_sweeps = strategy_sweeps if strategy_sweeps is not None else STRATEGY_SWEEPS
        self._researcher: AutoResearcher | None = None
        self._completed_keys: set[str] = set()
        self._experiment_count = 0
        self._error_count = 0
        self._timeout_count = 0
        self._total_expected = 0
        self._audit_enabled = audit
        self._audit: AuditTrail | None = None
        self._memory_db = memory_db
        self._memory = None
        self._run_id = None

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    @property
    def experiments_path(self) -> str:
        return os.path.join(self.results_dir, 'experiments.json')

    @property
    def errors_path(self) -> str:
        return os.path.join(self.results_dir, 'errors.log')

    @property
    def summary_path(self) -> str:
        return os.path.join(self.results_dir, 'summary.md')

    @property
    def best_strategies_path(self) -> str:
        return os.path.join(self.results_dir, 'best_strategies.json')

    @property
    def run_log_path(self) -> str:
        return os.path.join(self.results_dir, 'run_log.txt')

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _log(self, message: str) -> None:
        """Log a timestamped message to run_log.txt and stdout."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        line = f'[{timestamp}] {message}'
        print(line, flush=True)
        try:
            with open(self.run_log_path, 'a') as f:
                f.write(line + '\n')
        except OSError:
            pass

    def _log_error(self, strategy_name: str, params: dict, error: str) -> None:
        """Log an error to errors.log."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            with open(self.errors_path, 'a') as f:
                f.write(f'[{timestamp}] Strategy: {strategy_name}\n')
                f.write(f'  Params: {params}\n')
                f.write(f'  Error: {error}\n')
                f.write('\n')
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Resume logic
    # ------------------------------------------------------------------

    @staticmethod
    def _experiment_key(strategy_name: str, params: dict) -> str:
        """Create a unique key for a strategy+params combination."""
        # Sort params for consistent keys
        sorted_params = sorted(params.items())
        return f'{strategy_name}|{sorted_params}'

    def _load_resume_state(self) -> int:
        """Load previous experiments and build the completed keys set.

        Returns the number of previously completed experiments.
        """
        if not os.path.exists(self.experiments_path):
            return 0

        try:
            self._researcher.load(self.experiments_path)
            for exp in self._researcher.log.experiments:
                key = self._experiment_key(exp.strategy_name, exp.params)
                self._completed_keys.add(key)
            count = len(self._completed_keys)
            self._experiment_count = count
            return count
        except Exception as exc:
            self._log(f'Warning: could not load resume state: {exc}')
            return 0

    def _is_completed(self, strategy_name: str, params: dict) -> bool:
        """Check if a strategy+params combo has already been tested."""
        key = self._experiment_key(strategy_name, params)
        return key in self._completed_keys

    def _mark_completed(self, strategy_name: str, params: dict) -> None:
        """Mark a strategy+params combo as completed."""
        key = self._experiment_key(strategy_name, params)
        self._completed_keys.add(key)

    # ------------------------------------------------------------------
    # Timeout-wrapped experiment
    # ------------------------------------------------------------------

    def _run_with_timeout(self, fn, timeout: int):
        """Run a function with a timeout using threading.

        Returns the function's return value or raises _ExperimentTimeoutError.
        """
        result = [None]
        exception = [None]

        def target():
            try:
                result[0] = fn()
            except Exception as exc:
                exception[0] = exc

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            # Thread is still running — timeout
            raise _ExperimentTimeoutError(
                f'Experiment exceeded {timeout}s timeout'
            )

        if exception[0] is not None:
            raise exception[0]

        return result[0]

    # ------------------------------------------------------------------
    # Single experiment (with resilience)
    # ------------------------------------------------------------------

    def _run_single_experiment(
        self,
        strategy_name: str,
        factory,
        params: dict,
    ) -> bool:
        """Run a single experiment with full resilience.

        Returns True if the experiment completed (success or skip),
        False on error/timeout.
        """
        label = f'{strategy_name} ({", ".join(f"{k}={v}" for k, v in params.items())})'

        # Check if already completed
        if self._is_completed(label, params):
            if self._audit:
                self._audit.experiment_skipped(label, params, 'already completed (resume)')
            return True

        # Check if memory says to skip
        if self._memory is not None:
            try:
                skip, reason = self._memory.should_skip(self.ticker, label, params)
                if skip:
                    self._log(f'Skipping {label}: {reason}')
                    if self._audit:
                        self._audit.experiment_skipped(label, params, reason)
                    return True
            except Exception:
                pass

        self._experiment_count += 1
        progress = f'Experiment {self._experiment_count}/{self._total_expected}'

        try:
            def do_experiment():
                strategy_fn = factory(**params)
                return self._researcher.run_experiment(
                    strategy_fn, label, params=params,
                )

            exp = self._run_with_timeout(do_experiment, self.experiment_timeout)

            status = '✅ KEPT' if exp.kept else '❌'
            train_sharpe = getattr(exp.train_result, 'sharpe_ratio', 0)
            test_sharpe = getattr(exp.test_result, 'sharpe_ratio', 0) if exp.test_result else 'N/A'
            test_str = (
                test_sharpe if isinstance(test_sharpe, str)
                else f"{test_sharpe:.4f}"
            )
            self._log(
                f'{progress} | {label} | train={train_sharpe:.4f}'
                f' test={test_str} | {status}'
            )

            self._mark_completed(label, params)

            # Store in memory
            if self._memory is not None and self._run_id is not None:
                try:
                    self._memory.store_experiment(exp, self._run_id, self.ticker)
                except Exception:
                    pass

            # Save after experiment
            if self._experiment_count % self.save_every == 0:
                self._save_state()

            return True

        except _ExperimentTimeoutError as exc:
            self._timeout_count += 1
            self._log(f'{progress} | {label} | ⏰ TIMEOUT ({self.experiment_timeout}s)')
            self._log_error(label, params, str(exc))
            if self._audit:
                self._audit.experiment_timeout(label, params, self.experiment_timeout)
            return False

        except Exception as exc:
            self._error_count += 1
            tb = traceback.format_exc()
            self._log(f'{progress} | {label} | 💥 ERROR: {exc}')
            self._log_error(label, params, tb)
            if self._audit:
                self._audit.experiment_failed(label, params, str(exc), tb)
            return False

    # ------------------------------------------------------------------
    # Save state
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        """Save current researcher state and update summary/best files."""
        try:
            self._researcher.save(self.experiments_path)
        except Exception as exc:
            self._log(f'Warning: failed to save experiments: {exc}')

        try:
            self._update_summary()
        except Exception:
            pass

        try:
            self._update_best_strategies()
        except Exception:
            pass

    def _update_summary(self) -> None:
        """Write a human-readable summary.md."""
        log = self._researcher.log
        kept = [e for e in log.experiments if e.kept]
        lines = [
            f'# AutoResearch Summary — {self.ticker}',
            '',
            f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            '',
            '## Progress',
            f'- Total experiments: {log.total_experiments}',
            f'- Errors: {self._error_count}',
            f'- Timeouts: {self._timeout_count}',
            f'- Best train Sharpe: {log.best_train_sharpe:.4f}',
            f'- Best test Sharpe: {log.best_test_sharpe:.4f}',
            '',
        ]

        if kept:
            lines.append('## Best Strategies Found')
            lines.append('')
            for e in kept:
                train_s = getattr(e.train_result, 'sharpe_ratio', 0)
                test_s = getattr(e.test_result, 'sharpe_ratio', 0) if e.test_result else 'N/A'
                lines.append(f'### {e.strategy_name}')
                lines.append(f'- Params: `{e.params}`')
                lines.append(f'- Train Sharpe: {train_s:.4f}')
                test_str = test_s if isinstance(test_s, str) else f"{test_s:.4f}"
                lines.append(f'- Test Sharpe: {test_str}')
                lines.append(f'- Reason: {e.reason}')
                lines.append('')
        else:
            lines.append('## No strategies beat the baseline yet.')
            lines.append('')

        with open(self.summary_path, 'w') as f:
            f.write('\n'.join(lines))

    def _update_best_strategies(self) -> None:
        """Write best_strategies.json with top strategies found so far."""
        kept = [e for e in self._researcher.log.experiments if e.kept]
        best = []
        for e in kept:
            best.append({
                'strategy_name': e.strategy_name,
                'params': e.params,
                'train_sharpe': getattr(e.train_result, 'sharpe_ratio', 0),
                'test_sharpe': getattr(e.test_result, 'sharpe_ratio', 0) if e.test_result else None,
                'reason': e.reason,
            })
        with open(self.best_strategies_path, 'w') as f:
            json.dump(best, f, indent=2)

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """Execute the full overnight research program.

        Returns a dict with summary statistics.
        """
        # 1. Create results directory
        os.makedirs(self.results_dir, exist_ok=True)

        # Initialize research memory
        try:
            memory_path = os.path.join(self.results_dir, self._memory_db)
            self._memory = ResearchMemory(memory_path)
            self._run_id = self._memory.start_run(self.ticker)
        except Exception as exc:
            self._log(f'Warning: could not initialize research memory: {exc}')
            self._memory = None
            self._run_id = None

        self._log(f'Starting overnight autoresearch for {self.ticker}')
        self._log(f'Results directory: {self.results_dir}')
        self._log(f'Experiment timeout: {self.experiment_timeout}s')
        self._log(f'Slippage: {self.slippage_pct}%')

        # 2. Initialize AutoResearcher
        init_kwargs = {
            'ticker': self.ticker,
            'total_period': self.total_period,
            'min_trades_train': 20,
            'min_trades_test': 10,
        }
        if self._candles is not None:
            init_kwargs['candles'] = self._candles
            # Don't pass ticker/total_period with candles
            init_kwargs.pop('ticker', None)
            init_kwargs.pop('total_period', None)
        if self._cross_validate_tickers is not None:
            init_kwargs['cross_validate_tickers'] = self._cross_validate_tickers

        # Initialize audit trail
        if self._audit_enabled:
            audit_dir = os.path.join(self.results_dir, 'audit')
            self._audit = AuditTrail(audit_dir=audit_dir)
            init_kwargs['audit'] = self._audit

        self._researcher = AutoResearcher(**init_kwargs)

        # Start audit run
        if self._audit:
            run_id = self._run_id or 0
            self._audit.start_run(run_id, self.ticker, {
                'total_period': self.total_period,
                'experiment_timeout': self.experiment_timeout,
                'total_sweeps': len(self.strategy_sweeps),
            })

        # 3. Calculate total expected experiments
        self._total_expected = sum(
            _count_combos(sweep['grid']) for sweep in self.strategy_sweeps
        )
        self._log(f'Total parameter combinations to test: {self._total_expected}')

        # 4. Check for resume state
        resumed = self._load_resume_state()
        if resumed > 0:
            self._log(f'Resuming from experiment #{resumed}')

        # 5. Run through all strategy sweeps
        for sweep in self.strategy_sweeps:
            strategy_name = sweep['name']
            factory = sweep['factory']
            grid = sweep['grid']
            combos = _grid_combos(grid)
            n_combos = len(combos)

            self._log(f'Starting {strategy_name} sweep ({n_combos} combos)...')

            if self._audit:
                self._audit.sweep_started(strategy_name, grid, n_combos)

            for params in combos:
                self._run_single_experiment(strategy_name, factory, params)

            # Count kept from this sweep
            if self._audit:
                kept_exps = [e for e in self._researcher.log.experiments if e.kept]
                best_sharpe = max(
                    (getattr(e.test_result, 'sharpe_ratio', 0) for e in kept_exps if e.test_result),
                    default=None,
                )
                self._audit.sweep_completed(strategy_name, n_combos, len(kept_exps), best_sharpe)

            self._log(f'Completed {strategy_name} sweep')

        # 6. Validate best
        self._log('Running validation on best strategies...')
        try:
            validated = self._researcher.validate_best(n=5)
            for exp in validated:
                val_sharpe = (
                    getattr(exp.validate_result, 'sharpe_ratio', 'N/A')
                    if exp.validate_result else 'N/A'
                )
                self._log(f'  Validated: {exp.strategy_name} | validate_sharpe={val_sharpe}')
        except Exception as exc:
            self._log(f'Validation failed: {exc}')

        # 7. Final save
        self._save_state()

        # 8. Generate final report
        self._log('Generating final report...')
        try:
            report = self._researcher.report()
            report_path = os.path.join(self.results_dir, 'final_report.txt')
            with open(report_path, 'w') as f:
                f.write(report)
        except Exception as exc:
            self._log(f'Report generation failed: {exc}')

        # 9. Generate memory insights and priorities
        if self._memory is not None and self._run_id is not None:
            try:
                new_insights = self._memory.generate_insights(self._run_id)
                self._log(f'Generated {len(new_insights)} new insights')
                new_priorities = self._memory.generate_priorities(self._run_id)
                self._log(f'Generated {len(new_priorities)} new priorities')
                self._memory.end_run(self._run_id, status='completed')
                memory_stats = self._memory.stats()
                self._log(f'Memory stats: {memory_stats}')
            except Exception as exc:
                self._log(f'Warning: memory finalization failed: {exc}')
                try:
                    self._memory.end_run(self._run_id, status='completed')
                except Exception:
                    pass

        # End audit trail
        if self._audit:
            self._audit.end_run({
                'total_experiments': self._researcher.log.total_experiments,
                'errors': self._error_count,
                'timeouts': self._timeout_count,
                'best_train_sharpe': self._researcher.log.best_train_sharpe,
                'best_test_sharpe': self._researcher.log.best_test_sharpe,
                'kept_strategies': len([e for e in self._researcher.log.experiments if e.kept]),
            })

        # 10. Summary
        result = {
            'total_experiments': self._researcher.log.total_experiments,
            'errors': self._error_count,
            'timeouts': self._timeout_count,
            'best_train_sharpe': self._researcher.log.best_train_sharpe,
            'best_test_sharpe': self._researcher.log.best_test_sharpe,
            'kept_strategies': len([e for e in self._researcher.log.experiments if e.kept]),
        }

        if self._memory is not None:
            result['memory_stats'] = self._memory.stats()

        self._log(f'Overnight run complete! {result}')
        return result
