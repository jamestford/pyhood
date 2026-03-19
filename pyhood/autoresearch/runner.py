"""AutoResearcher — automated trading strategy discovery engine.

Inspired by Andrej Karpathy's approach to automated research: define the
search space, automate the experiments, and let the machine grind through
parameter combinations while you sleep.
"""

from __future__ import annotations

import inspect
import itertools
import json
import logging
import math
from datetime import datetime, timezone

from pyhood.backtest.engine import Backtester
from pyhood.backtest.models import BacktestResult, Trade
from pyhood.models import Candle

from .models import ExperimentLog, ExperimentResult

logger = logging.getLogger(__name__)

# Ticker groups for automatic cross-validation defaults
_EQUITY_INDEX_ETFS = {'SPY', 'QQQ', 'DIA', 'IWM', 'VOO'}
_EQUITY_CV_DEFAULTS = ['SPY', 'QQQ', 'DIA']
_CRYPTO_TICKERS = {'BTC-USD', 'ETH-USD', 'SOL-USD'}
_CRYPTO_CV_DEFAULTS = ['BTC-USD', 'ETH-USD', 'SOL-USD']


def _default_cross_validate_tickers(ticker: str) -> list[str] | None:
    """Return default cross-validation tickers based on the primary ticker."""
    upper = ticker.upper()
    if upper in _EQUITY_INDEX_ETFS:
        return [t for t in _EQUITY_CV_DEFAULTS if t != upper]
    if upper in _CRYPTO_TICKERS:
        return [t for t in _CRYPTO_CV_DEFAULTS if t != upper]
    return None


class AutoResearcher:
    """Automated trading strategy discovery engine.

    Splits historical data into train/test/validate sets and systematically
    searches for strategies that generalise — not just ones that look good
    on past data.

    Usage with yfinance::

        researcher = AutoResearcher(ticker='SPY', total_period='10y')

    Usage with pre-loaded candles (for testing)::

        researcher = AutoResearcher(candles=my_candles)

    Args:
        ticker: Symbol to fetch via yfinance (ignored when *candles* given).
        total_period: yfinance period string (e.g. '10y', '5y').
        train_pct: Fraction of data for training (default 0.50).
        test_pct: Fraction of data for testing (default 0.25).
        validate_pct: Fraction of data for validation (default 0.25).
        metric: BacktestResult attribute used to rank experiments.
        min_trades_train: Minimum trades on train split (default 20).
        min_trades_test: Minimum trades on test/validate splits (default 10).
        candles: Pre-loaded candle list. Overrides *ticker*/*total_period*.
        initial_capital: Starting capital for each backtest.
        top_n: Number of top train results to forward to test (default 3).
    """

    def __init__(
        self,
        ticker: str = 'SPY',
        total_period: str = '10y',
        train_pct: float = 0.50,
        test_pct: float = 0.25,
        validate_pct: float = 0.25,
        metric: str = 'sharpe_ratio',
        min_trades: int | None = None,
        min_trades_train: int = 20,
        min_trades_test: int = 10,
        candles: list[Candle] | None = None,
        initial_capital: float = 10000.0,
        top_n: int = 3,
        cross_validate_tickers: list[str] | None = None,
        cross_validate_min_pass: int = 2,
        cross_validate_min_sharpe: float = 0.5,
    ):
        if abs(train_pct + test_pct + validate_pct - 1.0) > 1e-6:
            raise ValueError("train_pct + test_pct + validate_pct must equal 1.0")

        self.ticker = ticker
        self.metric = metric
        # Backward compat: if old min_trades is passed, use it for both
        if min_trades is not None:
            self.min_trades_train = min_trades
            self.min_trades_test = min_trades
        else:
            self.min_trades_train = min_trades_train
            self.min_trades_test = min_trades_test
        self.initial_capital = initial_capital
        self.top_n = top_n
        self._train_pct = train_pct
        self._test_pct = test_pct
        self._validate_pct = validate_pct
        self.cross_validate_min_pass = cross_validate_min_pass
        self.cross_validate_min_sharpe = cross_validate_min_sharpe

        # Fetch or accept candles
        if candles is not None:
            all_candles = sorted(candles, key=lambda c: c.begins_at)
        else:
            bt = Backtester.from_yfinance(ticker, period=total_period,
                                          initial_capital=initial_capital)
            all_candles = bt.candles
            self.ticker = bt.symbol

        self.all_candles = all_candles
        self.train_candles, self.test_candles, self.validate_candles = \
            self.split_data(all_candles)

        # Cross-validation setup
        self._cross_validators: dict[str, Backtester] = {}
        self._cross_validate_tickers: list[str] | None = cross_validate_tickers
        # Resolve defaults if not explicitly provided
        if cross_validate_tickers is None:
            self._cross_validate_tickers = _default_cross_validate_tickers(self.ticker)
        # Fetch cross-validation data
        if self._cross_validate_tickers:
            self._init_cross_validators(total_period)

        # Experiment log
        self.log = ExperimentLog(
            ticker=self.ticker,
        )
        self._next_id = 1

    def _init_cross_validators(self, total_period: str = '10y') -> None:
        """Initialize Backtester instances for cross-validation tickers."""
        for cv_ticker in (self._cross_validate_tickers or []):
            try:
                bt = Backtester.from_yfinance(
                    cv_ticker, period=total_period,
                    initial_capital=self.initial_capital,
                )
                self._cross_validators[cv_ticker] = bt
            except Exception as exc:
                logger.warning(
                    "Failed to fetch cross-validation data for %s: %s",
                    cv_ticker, exc,
                )

    def set_cross_validators(self, validators: dict[str, Backtester]) -> None:
        """Manually set cross-validation Backtester instances (e.g. for testing).

        Args:
            validators: Dict mapping ticker symbol to a Backtester instance.
        """
        self._cross_validators = dict(validators)
        self._cross_validate_tickers = list(validators.keys())

    # ------------------------------------------------------------------
    # Data splitting
    # ------------------------------------------------------------------

    def split_data(
        self, candles: list[Candle]
    ) -> tuple[list[Candle], list[Candle], list[Candle]]:
        """Split candle list into train / test / validate by date order.

        Returns:
            Tuple of (train_candles, test_candles, validate_candles).
        """
        n = len(candles)
        train_end = int(n * self._train_pct)
        test_end = train_end + int(n * self._test_pct)

        train = candles[:train_end]
        test = candles[train_end:test_end]
        validate = candles[test_end:]
        return train, test, validate

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        strategy_fn,
        strategy_name: str = 'Strategy',
        dataset: str = 'train',
    ) -> BacktestResult:
        """Run a single backtest on the specified dataset split.

        Args:
            strategy_fn: Strategy callable ``(candles, position) -> signal``.
            strategy_name: Label for the backtest result.
            dataset: One of ``'train'``, ``'test'``, ``'validate'``.

        Returns:
            BacktestResult from the backtest engine.
        """
        data_map = {
            'train': self.train_candles,
            'test': self.test_candles,
            'validate': self.validate_candles,
        }
        if dataset not in data_map:
            raise ValueError(f"dataset must be one of {list(data_map)}")

        candles = data_map[dataset]
        if not candles:
            raise ValueError(f"No candles in the '{dataset}' split")

        bt = Backtester(candles, initial_capital=self.initial_capital)
        return bt.run(strategy_fn, strategy_name)

    # ------------------------------------------------------------------
    # Single experiment
    # ------------------------------------------------------------------

    def run_experiment(
        self,
        strategy_fn,
        strategy_name: str = 'Strategy',
        params: dict | None = None,
        strategy_code: str = '',
    ) -> ExperimentResult:
        """Run a single experiment through the train → test pipeline.

        1. Backtest on **train** data.
        2. If train metric beats current best *and* min_trades met,
           backtest on **test** data.
        3. If test metric also beats current best, mark as *kept*.
        4. Log everything regardless.

        Returns:
            ExperimentResult with all details.
        """
        params = params or {}
        exp_id = self._next_id
        self._next_id += 1

        # --- Train ---
        train_result = self.evaluate(strategy_fn, strategy_name, 'train')
        train_metric = getattr(train_result, self.metric)

        test_result: BacktestResult | None = None
        kept = False
        reason = ''

        # Check min_trades
        if train_result.total_trades < self.min_trades_train:
            reason = (f"Discarded: only {train_result.total_trades} trades "
                      f"(min {self.min_trades_train})")
        elif train_metric <= self.log.best_train_sharpe:
            reason = (f"Discarded: train {self.metric}={train_metric:.4f} "
                      f"<= best {self.log.best_train_sharpe:.4f}")
        else:
            # Promoted to test
            test_result = self.evaluate(strategy_fn, strategy_name, 'test')
            test_metric = getattr(test_result, self.metric)

            if test_result.total_trades < self.min_trades_test:
                reason = (f"Discarded: test trades={test_result.total_trades} "
                          f"< min {self.min_trades_test}")
            elif test_metric > self.log.best_test_sharpe:
                kept = True
                self.log.best_train_sharpe = train_metric
                self.log.best_test_sharpe = test_metric

                # Overfitting check
                if train_metric != 0:
                    gap = abs(train_metric - test_metric) / abs(train_metric)
                else:
                    gap = 0.0
                if gap > 0.30:
                    reason = (f"KEPT (⚠️ overfit warning: train={train_metric:.4f}, "
                              f"test={test_metric:.4f}, gap={gap:.0%})")
                else:
                    reason = (f"KEPT: train={train_metric:.4f}, "
                              f"test={test_metric:.4f}")
            else:
                reason = (f"Discarded: test {self.metric}={test_metric:.4f} "
                          f"<= best {self.log.best_test_sharpe:.4f}")

        experiment = ExperimentResult(
            experiment_id=exp_id,
            strategy_code=strategy_code or _extract_code(strategy_fn),
            strategy_name=strategy_name,
            params=params,
            train_result=train_result,
            test_result=test_result,
            kept=kept,
            reason=reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self.log.experiments.append(experiment)
        self.log.total_experiments += 1
        return experiment

    # ------------------------------------------------------------------
    # Parameter sweeps
    # ------------------------------------------------------------------

    def parameter_sweep(
        self,
        strategy_factory,
        param_name: str,
        param_values: list,
        base_params: dict | None = None,
        strategy_name: str = 'Strategy',
    ) -> list[ExperimentResult]:
        """Sweep a single parameter across values.

        1. Run all combinations on **train** data.
        2. Forward top-N (by train metric) to **test** data.

        Returns:
            List of ExperimentResult sorted by test performance (best first).
            Experiments that were not tested sort last.
        """
        base_params = dict(base_params or {})
        experiments: list[ExperimentResult] = []

        # Phase 1 — train sweep
        train_scores: list[tuple[float, int, ExperimentResult]] = []
        for value in param_values:
            params = {**base_params, param_name: value}
            label = f"{strategy_name} ({param_name}={value})"
            strategy_fn = strategy_factory(**params)
            code = _extract_factory_call(strategy_factory, params)

            exp_id = self._next_id
            self._next_id += 1

            train_result = self.evaluate(strategy_fn, label, 'train')
            train_metric = getattr(train_result, self.metric)

            exp = ExperimentResult(
                experiment_id=exp_id,
                strategy_code=code,
                strategy_name=label,
                params=params,
                train_result=train_result,
                kept=False,
                reason='train-only',
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            experiments.append(exp)
            if train_result.total_trades >= self.min_trades_train:
                train_scores.append((train_metric, exp_id, exp))

        # Phase 2 — test top N
        train_scores.sort(key=lambda t: t[0], reverse=True)
        for rank, (score, eid, exp) in enumerate(train_scores[:self.top_n]):
            params = exp.params
            strategy_fn = strategy_factory(**params)
            test_result = self.evaluate(strategy_fn, exp.strategy_name, 'test')
            test_metric = getattr(test_result, self.metric)
            exp.test_result = test_result

            if test_result.total_trades < self.min_trades_test:
                exp.reason = (f"Discarded: test trades={test_result.total_trades} "
                              f"< min {self.min_trades_test}")
            elif test_metric > self.log.best_test_sharpe:
                exp.kept = True
                self.log.best_train_sharpe = score
                self.log.best_test_sharpe = test_metric
                train_m = score
                if train_m != 0:
                    gap = abs(train_m - test_metric) / abs(train_m)
                else:
                    gap = 0.0
                if gap > 0.30:
                    exp.reason = (f"KEPT (⚠️ overfit warning: train={train_m:.4f}, "
                                  f"test={test_metric:.4f}, gap={gap:.0%})")
                else:
                    exp.reason = (f"KEPT: train={train_m:.4f}, test={test_metric:.4f}")
            else:
                exp.reason = (f"Discarded: test {self.metric}={test_metric:.4f} "
                              f"<= best {self.log.best_test_sharpe:.4f}")

        # Log all experiments
        for exp in experiments:
            self.log.experiments.append(exp)
            self.log.total_experiments += 1

        # Sort: tested experiments (by test metric desc), then untested
        def sort_key(e: ExperimentResult):
            if e.test_result is not None:
                return (1, getattr(e.test_result, self.metric))
            return (0, getattr(e.train_result, self.metric))

        experiments.sort(key=sort_key, reverse=True)
        return experiments

    def multi_param_sweep(
        self,
        strategy_factory,
        param_grid: dict[str, list],
        strategy_name: str = 'Strategy',
    ) -> list[ExperimentResult]:
        """Grid search across multiple parameters.

        Args:
            strategy_factory: Callable that accepts keyword params and returns
                a strategy function.
            param_grid: Dict mapping param name to list of values.
                Example: ``{'fast': [5,7,9], 'slow': [15,20,25]}``
            strategy_name: Base name for labelling.

        Returns:
            List of ExperimentResult sorted by test performance.
        """
        keys = list(param_grid.keys())
        value_lists = [param_grid[k] for k in keys]
        experiments: list[ExperimentResult] = []

        # Phase 1 — train sweep all combos
        train_scores: list[tuple[float, ExperimentResult]] = []
        for combo in itertools.product(*value_lists):
            params = dict(zip(keys, combo))
            param_str = ', '.join(f'{k}={v}' for k, v in params.items())
            label = f"{strategy_name} ({param_str})"
            strategy_fn = strategy_factory(**params)
            code = _extract_factory_call(strategy_factory, params)

            exp_id = self._next_id
            self._next_id += 1

            train_result = self.evaluate(strategy_fn, label, 'train')
            train_metric = getattr(train_result, self.metric)

            exp = ExperimentResult(
                experiment_id=exp_id,
                strategy_code=code,
                strategy_name=label,
                params=params,
                train_result=train_result,
                kept=False,
                reason='train-only',
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            experiments.append(exp)
            if train_result.total_trades >= self.min_trades_train:
                train_scores.append((train_metric, exp))

        # Phase 2 — test top N
        train_scores.sort(key=lambda t: t[0], reverse=True)
        for score, exp in train_scores[:self.top_n]:
            params = exp.params
            strategy_fn = strategy_factory(**params)
            test_result = self.evaluate(strategy_fn, exp.strategy_name, 'test')
            test_metric = getattr(test_result, self.metric)
            exp.test_result = test_result

            if test_result.total_trades < self.min_trades_test:
                exp.reason = (f"Discarded: test trades={test_result.total_trades} "
                              f"< min {self.min_trades_test}")
            elif test_metric > self.log.best_test_sharpe:
                exp.kept = True
                self.log.best_train_sharpe = score
                self.log.best_test_sharpe = test_metric
                if score != 0:
                    gap = abs(score - test_metric) / abs(score)
                else:
                    gap = 0.0
                if gap > 0.30:
                    exp.reason = (f"KEPT (⚠️ overfit warning: train={score:.4f}, "
                                  f"test={test_metric:.4f}, gap={gap:.0%})")
                else:
                    exp.reason = f"KEPT: train={score:.4f}, test={test_metric:.4f}"
            else:
                exp.reason = (f"Discarded: test {self.metric}={test_metric:.4f} "
                              f"<= best {self.log.best_test_sharpe:.4f}")

        for exp in experiments:
            self.log.experiments.append(exp)
            self.log.total_experiments += 1

        def sort_key(e: ExperimentResult):
            if e.test_result is not None:
                return (1, getattr(e.test_result, self.metric))
            return (0, getattr(e.train_result, self.metric))

        experiments.sort(key=sort_key, reverse=True)
        return experiments

    # ------------------------------------------------------------------
    # Cross-validation
    # ------------------------------------------------------------------

    def cross_validate(self, strategy_fn, strategy_name: str) -> dict:
        """Run strategy on all cross-validation tickers.

        Runs the strategy on the FULL data of each cross-validation ticker
        (not split — this is a robustness check, not optimization).

        A ticker passes if:
        - sharpe >= cross_validate_min_sharpe
        - total_return > 0
        - total_trades >= min_trades_test

        Returns:
            Dict with keys: 'passed', 'results', 'pass_count', 'required'.
        """
        if not self._cross_validators:
            return {
                'passed': True,
                'results': {},
                'pass_count': 0,
                'required': 0,
            }

        results: dict[str, dict] = {}
        pass_count = 0

        for ticker, bt in self._cross_validators.items():
            try:
                backtest_result = bt.run(strategy_fn, strategy_name)
                ticker_passed = (
                    backtest_result.sharpe_ratio >= self.cross_validate_min_sharpe
                    and backtest_result.total_return > 0
                    and backtest_result.total_trades >= self.min_trades_test
                )
                results[ticker] = {
                    'sharpe': round(backtest_result.sharpe_ratio, 4),
                    'return': round(backtest_result.total_return, 2),
                    'trades': backtest_result.total_trades,
                    'passed': ticker_passed,
                }
                if ticker_passed:
                    pass_count += 1
            except Exception as exc:
                logger.warning(
                    "Cross-validation failed for %s: %s", ticker, exc,
                )
                results[ticker] = {
                    'sharpe': 0.0,
                    'return': 0.0,
                    'trades': 0,
                    'passed': False,
                    'error': str(exc),
                }

        required = self.cross_validate_min_pass
        return {
            'passed': pass_count >= required,
            'results': results,
            'pass_count': pass_count,
            'required': required,
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_best(self, n: int = 3) -> list[ExperimentResult]:
        """Validate the top-N experiments on the held-out validate set.

        Only experiments that have a test_result are eligible.

        Returns:
            List of ExperimentResult with validate_result populated,
            sorted by validate metric descending.
        """
        tested = [e for e in self.log.experiments if e.test_result is not None]
        tested.sort(
            key=lambda e: getattr(e.test_result, self.metric),
            reverse=True,
        )

        results = []
        for exp in tested[:n]:
            params = exp.params
            # We need to re-create the strategy — extract factory info from code
            # For robustness, just re-evaluate on validate set
            # The caller should use the same factory; here we store the result
            # by running evaluate with a simple approach
            code = exp.strategy_code
            # Try to reconstruct the strategy from params + code
            strategy_fn = _reconstruct_strategy(exp)
            if strategy_fn is None:
                exp.validate_result = None
                exp.reason += ' | validate: could not reconstruct strategy'
                results.append(exp)
                continue

            validate_result = self.evaluate(
                strategy_fn, exp.strategy_name, 'validate'
            )
            exp.validate_result = validate_result
            val_metric = getattr(validate_result, self.metric)
            exp.reason += f' | validate {self.metric}={val_metric:.4f}'

            # Cross-validation
            if self._cross_validators:
                cv_result = self.cross_validate(strategy_fn, exp.strategy_name)
                exp.cross_validation = cv_result
                if cv_result['passed']:
                    exp.reason += ' | cross-validation PASSED'
                else:
                    exp.reason += (
                        f' | cross-validation FAILED '
                        f'({cv_result["pass_count"]}/{cv_result["required"]} passed)'
                    )

            results.append(exp)

        results.sort(
            key=lambda e: getattr(e.validate_result, self.metric, float('-inf')),
            reverse=True,
        )
        return results

    # ------------------------------------------------------------------
    # Screening integration
    # ------------------------------------------------------------------

    def run_with_screening(
        self,
        filters: dict,
        universe: str | list[str] = 'sp500',
        max_tickers: int = 5,
        strategy_factories: list | None = None,
    ) -> dict:
        """Screen for tickers, then run autoresearch on each.

        1. Screen *universe* with fundamental *filters*.
        2. For the top *max_tickers* results, create a new AutoResearcher
           per ticker and run parameter sweeps.
        3. Aggregate and rank results across all tickers.

        Args:
            filters: Fundamental filter dict (same format as
                ``FundamentalData.passes_filter``).
            universe: ``'sp500'``, ``'nasdaq100'``, or a list of tickers.
            max_tickers: Maximum tickers to research.
            strategy_factories: List of ``(factory, param_grid, name)``
                tuples.  Defaults to EMA crossover + MACD grids.

        Returns:
            Dict with ``'tickers'``, ``'results'`` (per-ticker experiment
            lists), and ``'ranked'`` (all experiments sorted by test metric).
        """
        from pyhood.screener import StockScreener

        screener = StockScreener(universe)
        tickers = screener.screen_for_autoresearch(
            filters, max_tickers=max_tickers
        )

        if not tickers:
            return {'tickers': [], 'results': {}, 'ranked': []}

        if strategy_factories is None:
            from pyhood.backtest.strategies import ema_crossover, macd_crossover
            strategy_factories = [
                (ema_crossover, {'fast': [5, 9, 13], 'slow': [21, 30, 50]}, 'EMA'),
                (macd_crossover, {'fast': [10, 12], 'slow': [24, 26], 'signal': [7, 9]}, 'MACD'),
            ]

        all_results: dict[str, list] = {}
        all_experiments = []

        for ticker in tickers:
            try:
                researcher = AutoResearcher(
                    ticker=ticker,
                    total_period='10y',
                    initial_capital=self.initial_capital,
                )
                ticker_experiments = []
                for factory, grid, name in strategy_factories:
                    exps = researcher.multi_param_sweep(
                        factory, grid, strategy_name=f'{name} ({ticker})'
                    )
                    ticker_experiments.extend(exps)
                all_results[ticker] = ticker_experiments
                all_experiments.extend(ticker_experiments)
            except Exception as exc:
                logger.warning("Screening research failed for %s: %s", ticker, exc)

        # Rank all experiments by test metric
        def _sort_key(e):
            if e.test_result is not None:
                return (1, getattr(e.test_result, self.metric))
            return (0, getattr(e.train_result, self.metric))

        all_experiments.sort(key=_sort_key, reverse=True)

        return {
            'tickers': tickers,
            'results': all_results,
            'ranked': all_experiments,
        }

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def report(self) -> str:
        """Generate a formatted summary of all experiments.

        Returns:
            Multi-line string report.
        """
        lines: list[str] = []
        lines.append('=' * 70)
        lines.append(f'  AutoResearch Report — {self.ticker}')
        lines.append(f'  Total experiments: {self.log.total_experiments}')
        lines.append(f'  Best train {self.metric}: {self.log.best_train_sharpe:.4f}')
        lines.append(f'  Best test  {self.metric}: {self.log.best_test_sharpe:.4f}')
        lines.append(f'  Data splits: train={len(self.train_candles)} '
                      f'test={len(self.test_candles)} '
                      f'validate={len(self.validate_candles)} bars')
        lines.append('=' * 70)

        # Kept experiments
        kept = [e for e in self.log.experiments if e.kept]
        if kept:
            lines.append('')
            lines.append('  ✅ KEPT STRATEGIES')
            lines.append('  ' + '-' * 40)
            for e in kept:
                train_m = getattr(e.train_result, self.metric)
                test_m = getattr(e.test_result, self.metric) if e.test_result else 'N/A'
                val_m = getattr(e.validate_result, self.metric) if e.validate_result else 'N/A'
                lines.append(f'  #{e.experiment_id} {e.strategy_name}')
                lines.append(f'     Params: {e.params}')
                lines.append(f'     Train {self.metric}: {train_m:.4f}')
                if isinstance(test_m, float):
                    lines.append(f'     Test  {self.metric}: {test_m:.4f}')
                    # Overfitting gap
                    if train_m != 0:
                        gap = abs(train_m - test_m) / abs(train_m)
                        flag = ' ⚠️ OVERFIT' if gap > 0.30 else ''
                        lines.append(f'     Gap: {gap:.0%}{flag}')
                if isinstance(val_m, float):
                    lines.append(f'     Validate {self.metric}: {val_m:.4f}')
                lines.append(f'     Trades: train={e.train_result.total_trades}'
                             + (f' test={e.test_result.total_trades}' if e.test_result else '')
                             + (f' val={e.validate_result.total_trades}' if e.validate_result else ''))
                # Cross-validation results
                if e.cross_validation and e.cross_validation.get('results'):
                    cv = e.cross_validation
                    status = '✅ PASSED' if cv['passed'] else '❌ FAILED'
                    lines.append(f'     Cross-validation: {status} '
                                 f'({cv["pass_count"]}/{cv["required"]} required)')
                    for cv_ticker, cv_data in cv['results'].items():
                        tick_status = '✅' if cv_data['passed'] else '❌'
                        lines.append(
                            f'       {tick_status} {cv_ticker}: '
                            f'Sharpe={cv_data["sharpe"]:.4f} '
                            f'Return={cv_data["return"]:.2f}% '
                            f'Trades={cv_data["trades"]}'
                        )
                    if not cv['passed']:
                        lines.append('     ⚠️ Strategy is ticker-specific — '
                                     'failed cross-validation robustness check')
                lines.append('')
        else:
            lines.append('')
            lines.append('  No strategies beat the baseline yet.')

        # All experiments summary
        lines.append('')
        lines.append('  ALL EXPERIMENTS')
        lines.append('  ' + '-' * 40)
        lines.append(f'  {"#":<4} {"Strategy":<40} {"Train":>8} {"Test":>8} {"Kept":>5}')
        for e in self.log.experiments:
            train_m = getattr(e.train_result, self.metric)
            test_m = getattr(e.test_result, self.metric) if e.test_result else None
            lines.append(
                f'  {e.experiment_id:<4} {e.strategy_name:<40} '
                f'{train_m:>8.4f} '
                f'{test_m:>8.4f}' if test_m is not None
                else f'  {e.experiment_id:<4} {e.strategy_name:<40} '
                     f'{train_m:>8.4f} {"---":>8}'
                + f' {"✅" if e.kept else "❌":>5}'
            )

        lines.append('')
        lines.append('=' * 70)

        report_str = '\n'.join(lines)
        print(report_str)
        return report_str

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str = 'autoresearch_results.json') -> None:
        """Save the full experiment log to JSON."""
        data = _log_to_dict(self.log)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def load(self, path: str = 'autoresearch_results.json') -> None:
        """Load a previous experiment log from JSON."""
        with open(path, 'r') as f:
            data = json.load(f)
        self.log = _dict_to_log(data)
        self._next_id = max(
            (e.experiment_id for e in self.log.experiments), default=0
        ) + 1


# ======================================================================
# Helpers
# ======================================================================

def _extract_code(fn) -> str:
    """Best-effort extraction of a function's source code."""
    try:
        return inspect.getsource(fn)
    except (OSError, TypeError):
        return repr(fn)


def _extract_factory_call(factory, params: dict) -> str:
    """Create a reproducible code string for a factory call."""
    name = getattr(factory, '__name__', repr(factory))
    param_str = ', '.join(f'{k}={v!r}' for k, v in params.items())
    return f'{name}({param_str})'


def _reconstruct_strategy(exp: ExperimentResult):
    """Try to reconstruct a strategy function from an ExperimentResult.

    This uses the strategy_code string which should be a factory call like
    ``ema_crossover(fast=9, slow=21)``.
    """
    # Import all built-in strategies into a namespace
    from pyhood.backtest import strategies as strat_mod

    code = exp.strategy_code
    # Safety: only allow known function calls
    ns = {name: getattr(strat_mod, name) for name in dir(strat_mod)
          if callable(getattr(strat_mod, name)) and not name.startswith('_')}

    try:
        fn = eval(code, {"__builtins__": {}}, ns)  # noqa: S307
        if callable(fn):
            return fn
    except Exception:
        pass

    # Fallback: try to use params with a known factory name
    for factory_name, factory_fn in ns.items():
        if factory_name in code:
            try:
                return factory_fn(**exp.params)
            except Exception:
                continue

    return None


# ======================================================================
# Serialization helpers
# ======================================================================

def _backtest_to_dict(r: BacktestResult) -> dict:
    """Convert a BacktestResult to a JSON-serializable dict."""
    return {
        'strategy_name': r.strategy_name,
        'symbol': r.symbol,
        'period': r.period,
        'total_return': r.total_return,
        'annual_return': r.annual_return,
        'sharpe_ratio': r.sharpe_ratio,
        'max_drawdown': r.max_drawdown,
        'win_rate': r.win_rate,
        'profit_factor': r.profit_factor if r.profit_factor != float('inf') else 'inf',
        'total_trades': r.total_trades,
        'avg_trade_return': r.avg_trade_return,
        'avg_win': r.avg_win,
        'avg_loss': r.avg_loss,
        'buy_hold_return': r.buy_hold_return,
        'alpha': r.alpha,
        'trades': [
            {
                'entry_date': t.entry_date,
                'exit_date': t.exit_date,
                'side': t.side,
                'entry_price': t.entry_price,
                'exit_price': t.exit_price,
                'quantity': t.quantity,
                'pnl': t.pnl,
                'pnl_pct': t.pnl_pct,
                'regime': t.regime,
            }
            for t in r.trades
        ],
        # Omit equity_curve for size (can be large)
        'equity_curve_len': len(r.equity_curve),
        'regime_breakdown': r.regime_breakdown,
    }


def _dict_to_backtest(d: dict) -> BacktestResult:
    """Reconstruct a BacktestResult from a dict (equity_curve not restored)."""
    pf = d.get('profit_factor', 0.0)
    if pf == 'inf':
        pf = float('inf')

    trades = [
        Trade(
            entry_date=t['entry_date'],
            exit_date=t['exit_date'],
            side=t['side'],
            entry_price=t['entry_price'],
            exit_price=t['exit_price'],
            quantity=t['quantity'],
            pnl=t['pnl'],
            pnl_pct=t['pnl_pct'],
            regime=t.get('regime', 'unknown'),
        )
        for t in d.get('trades', [])
    ]

    return BacktestResult(
        strategy_name=d['strategy_name'],
        symbol=d.get('symbol', ''),
        period=d.get('period', ''),
        total_return=d['total_return'],
        annual_return=d.get('annual_return', 0.0),
        sharpe_ratio=d['sharpe_ratio'],
        max_drawdown=d.get('max_drawdown', 0.0),
        win_rate=d.get('win_rate', 0.0),
        profit_factor=pf,
        total_trades=d.get('total_trades', 0),
        avg_trade_return=d.get('avg_trade_return', 0.0),
        avg_win=d.get('avg_win', 0.0),
        avg_loss=d.get('avg_loss', 0.0),
        buy_hold_return=d.get('buy_hold_return', 0.0),
        alpha=d.get('alpha', 0.0),
        trades=trades,
        equity_curve=[],
        regime_breakdown=d.get('regime_breakdown'),
    )


def _experiment_to_dict(e: ExperimentResult) -> dict:
    """Convert an ExperimentResult to a JSON-serializable dict."""
    return {
        'experiment_id': e.experiment_id,
        'strategy_code': e.strategy_code,
        'strategy_name': e.strategy_name,
        'params': e.params,
        'train_result': _backtest_to_dict(e.train_result),
        'test_result': _backtest_to_dict(e.test_result) if e.test_result else None,
        'validate_result': _backtest_to_dict(e.validate_result) if e.validate_result else None,
        'kept': e.kept,
        'reason': e.reason,
        'timestamp': e.timestamp,
        'cross_validation': e.cross_validation,
    }


def _dict_to_experiment(d: dict) -> ExperimentResult:
    """Reconstruct an ExperimentResult from a dict."""
    return ExperimentResult(
        experiment_id=d['experiment_id'],
        strategy_code=d.get('strategy_code', ''),
        strategy_name=d['strategy_name'],
        params=d.get('params', {}),
        train_result=_dict_to_backtest(d['train_result']),
        test_result=_dict_to_backtest(d['test_result']) if d.get('test_result') else None,
        validate_result=_dict_to_backtest(d['validate_result']) if d.get('validate_result') else None,
        kept=d.get('kept', False),
        reason=d.get('reason', ''),
        timestamp=d.get('timestamp', ''),
        cross_validation=d.get('cross_validation'),
    )


def _log_to_dict(log: ExperimentLog) -> dict:
    """Convert an ExperimentLog to a JSON-serializable dict."""
    return {
        'ticker': log.ticker,
        'total_experiments': log.total_experiments,
        'best_train_sharpe': log.best_train_sharpe,
        'best_test_sharpe': log.best_test_sharpe,
        'experiments': [_experiment_to_dict(e) for e in log.experiments],
    }


def _dict_to_log(d: dict) -> ExperimentLog:
    """Reconstruct an ExperimentLog from a dict."""
    return ExperimentLog(
        ticker=d.get('ticker', ''),
        total_experiments=d.get('total_experiments', 0),
        best_train_sharpe=d.get('best_train_sharpe', 0.0),
        best_test_sharpe=d.get('best_test_sharpe', 0.0),
        experiments=[_dict_to_experiment(e) for e in d.get('experiments', [])],
    )
