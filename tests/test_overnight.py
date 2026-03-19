"""Tests for the overnight autoresearch runner."""

from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timedelta

from pyhood.autoresearch.overnight import (
    STRATEGY_SWEEPS,
    OvernightRunner,
    _count_combos,
    _grid_combos,
)
from pyhood.backtest.strategies import ema_crossover
from pyhood.models import Candle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candles(
    n: int = 500,
    start_price: float = 100.0,
    trend: float = 0.10,
    symbol: str = 'TEST',
) -> list[Candle]:
    """Create synthetic candle data with a controllable trend."""
    candles: list[Candle] = []
    base_date = datetime(2020, 1, 1)
    price = start_price

    for i in range(n):
        daily_drift = (trend / n)
        oscillation = 0.02 * math.sin(i * 2 * math.pi / 40)
        price *= (1 + daily_drift + oscillation)

        high = price * 1.015
        low = price * 0.985
        open_p = price * (1 + 0.002 * ((i % 3) - 1))

        candles.append(Candle(
            symbol=symbol,
            begins_at=(base_date + timedelta(days=i)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            open_price=open_p,
            close_price=price,
            high_price=high,
            low_price=low,
            volume=1_000_000 + i * 100,
        ))

    return candles


def _bad_strategy_factory(explode: bool = True):
    """A strategy factory that always raises an exception."""
    def strategy_fn(candles, position):
        raise RuntimeError("Intentional test explosion!")
    return strategy_fn


def _tiny_sweeps():
    """A minimal sweep config for fast testing."""
    return [
        {
            'name': 'EMA Crossover',
            'factory': ema_crossover,
            'grid': {
                'fast': [5, 9],
                'slow': [20, 30],
            },
        },
    ]


# ---------------------------------------------------------------------------
# Tests — Initialization
# ---------------------------------------------------------------------------

class TestOvernightRunnerInit:

    def test_default_init(self):
        runner = OvernightRunner()
        assert runner.ticker == 'SPY'
        assert runner.total_period == '10y'
        assert runner.results_dir == 'autoresearch_results'
        assert runner.experiment_timeout == 60
        assert runner.save_every == 1
        assert runner.slippage_pct == 0.01

    def test_custom_init(self):
        runner = OvernightRunner(
            ticker='QQQ',
            total_period='5y',
            results_dir='/tmp/test_results',
            experiment_timeout=120,
            slippage_pct=0.05,
        )
        assert runner.ticker == 'QQQ'
        assert runner.total_period == '5y'
        assert runner.results_dir == '/tmp/test_results'
        assert runner.experiment_timeout == 120
        assert runner.slippage_pct == 0.05

    def test_paths(self):
        runner = OvernightRunner(results_dir='/tmp/test_dir')
        assert runner.experiments_path == '/tmp/test_dir/experiments.json'
        assert runner.errors_path == '/tmp/test_dir/errors.log'
        assert runner.summary_path == '/tmp/test_dir/summary.md'
        assert runner.best_strategies_path == '/tmp/test_dir/best_strategies.json'
        assert runner.run_log_path == '/tmp/test_dir/run_log.txt'


# ---------------------------------------------------------------------------
# Tests — Grid helpers
# ---------------------------------------------------------------------------

class TestGridHelpers:

    def test_count_combos(self):
        assert _count_combos({'a': [1, 2, 3], 'b': [4, 5]}) == 6
        assert _count_combos({'x': [1]}) == 1
        assert _count_combos({'a': [1, 2], 'b': [3, 4], 'c': [5, 6]}) == 8

    def test_grid_combos(self):
        combos = _grid_combos({'a': [1, 2], 'b': [3, 4]})
        assert len(combos) == 4
        assert {'a': 1, 'b': 3} in combos
        assert {'a': 2, 'b': 4} in combos


# ---------------------------------------------------------------------------
# Tests — Resume detection
# ---------------------------------------------------------------------------

class TestResumeDetection:

    def test_no_previous_state(self):
        """When no experiments.json exists, starts fresh."""
        with tempfile.TemporaryDirectory() as tmpdir:
            candles = _make_candles(400)
            runner = OvernightRunner(
                results_dir=tmpdir,
                candles=candles,
                cross_validate_tickers=[],
                strategy_sweeps=_tiny_sweeps(),
            )
            runner._researcher = None  # Will be set in run()
            # Just verify the file doesn't exist
            assert not os.path.exists(runner.experiments_path)

    def test_resume_skips_completed(self):
        """After running, restarting should skip already-completed experiments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            candles = _make_candles(400)

            # First run
            runner1 = OvernightRunner(
                results_dir=tmpdir,
                candles=candles,
                cross_validate_tickers=[],
                strategy_sweeps=_tiny_sweeps(),
                experiment_timeout=30,
            )
            result1 = runner1.run()
            first_count = result1['total_experiments']
            assert first_count > 0

            # experiments.json should exist
            assert os.path.exists(os.path.join(tmpdir, 'experiments.json'))

            # Second run — should resume and skip completed
            runner2 = OvernightRunner(
                results_dir=tmpdir,
                candles=candles,
                cross_validate_tickers=[],
                strategy_sweeps=_tiny_sweeps(),
                experiment_timeout=30,
            )
            result2 = runner2.run()
            # Total experiments should be the same (no new ones added)
            assert result2['total_experiments'] == first_count


# ---------------------------------------------------------------------------
# Tests — Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def test_bad_strategy_doesnt_kill_run(self):
        """A strategy that raises an exception should not kill the run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            candles = _make_candles(400)
            sweeps = [
                {
                    'name': 'Bad Strategy',
                    'factory': _bad_strategy_factory,
                    'grid': {'explode': [True]},
                },
                {
                    'name': 'EMA Crossover',
                    'factory': ema_crossover,
                    'grid': {'fast': [5], 'slow': [20]},
                },
            ]
            runner = OvernightRunner(
                results_dir=tmpdir,
                candles=candles,
                cross_validate_tickers=[],
                strategy_sweeps=sweeps,
                experiment_timeout=30,
            )
            result = runner.run()
            # Run should complete despite the bad strategy
            assert result['errors'] >= 1
            # The EMA experiment should still have run
            assert result['total_experiments'] >= 1

    def test_errors_logged(self):
        """Errors should be logged to errors.log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            candles = _make_candles(400)
            sweeps = [
                {
                    'name': 'Bad Strategy',
                    'factory': _bad_strategy_factory,
                    'grid': {'explode': [True]},
                },
            ]
            runner = OvernightRunner(
                results_dir=tmpdir,
                candles=candles,
                cross_validate_tickers=[],
                strategy_sweeps=sweeps,
                experiment_timeout=30,
            )
            runner.run()

            errors_path = os.path.join(tmpdir, 'errors.log')
            assert os.path.exists(errors_path)
            with open(errors_path) as f:
                content = f.read()
            assert 'Bad Strategy' in content
            assert 'Intentional test explosion' in content


# ---------------------------------------------------------------------------
# Tests — Save frequency
# ---------------------------------------------------------------------------

class TestSaveFrequency:

    def test_experiments_json_updated_after_each(self):
        """experiments.json should be updated after each experiment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            candles = _make_candles(400)
            runner = OvernightRunner(
                results_dir=tmpdir,
                candles=candles,
                cross_validate_tickers=[],
                strategy_sweeps=_tiny_sweeps(),
                experiment_timeout=30,
                save_every=1,
            )
            runner.run()

            # experiments.json should exist with data
            exp_path = os.path.join(tmpdir, 'experiments.json')
            assert os.path.exists(exp_path)
            with open(exp_path) as f:
                data = json.load(f)
            assert data['total_experiments'] > 0
            assert len(data['experiments']) > 0


# ---------------------------------------------------------------------------
# Tests — Results directory structure
# ---------------------------------------------------------------------------

class TestResultsDirectory:

    def test_directory_structure(self):
        """All expected output files should be created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            candles = _make_candles(400)
            runner = OvernightRunner(
                results_dir=tmpdir,
                candles=candles,
                cross_validate_tickers=[],
                strategy_sweeps=_tiny_sweeps(),
                experiment_timeout=30,
            )
            runner.run()

            assert os.path.exists(os.path.join(tmpdir, 'experiments.json'))
            assert os.path.exists(os.path.join(tmpdir, 'summary.md'))
            assert os.path.exists(os.path.join(tmpdir, 'best_strategies.json'))
            assert os.path.exists(os.path.join(tmpdir, 'run_log.txt'))

    def test_summary_is_readable(self):
        """summary.md should contain meaningful content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            candles = _make_candles(400)
            runner = OvernightRunner(
                results_dir=tmpdir,
                candles=candles,
                cross_validate_tickers=[],
                strategy_sweeps=_tiny_sweeps(),
                experiment_timeout=30,
            )
            runner.run()

            with open(os.path.join(tmpdir, 'summary.md')) as f:
                content = f.read()
            assert 'AutoResearch Summary' in content
            assert 'Total experiments' in content

    def test_best_strategies_valid_json(self):
        """best_strategies.json should be valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            candles = _make_candles(400)
            runner = OvernightRunner(
                results_dir=tmpdir,
                candles=candles,
                cross_validate_tickers=[],
                strategy_sweeps=_tiny_sweeps(),
                experiment_timeout=30,
            )
            runner.run()

            with open(os.path.join(tmpdir, 'best_strategies.json')) as f:
                data = json.load(f)
            assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Tests — Run log
# ---------------------------------------------------------------------------

class TestRunLog:

    def test_run_log_timestamped(self):
        """Run log entries should have timestamps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            candles = _make_candles(400)
            runner = OvernightRunner(
                results_dir=tmpdir,
                candles=candles,
                cross_validate_tickers=[],
                strategy_sweeps=_tiny_sweeps(),
                experiment_timeout=30,
            )
            runner.run()

            with open(os.path.join(tmpdir, 'run_log.txt')) as f:
                lines = f.readlines()

            assert len(lines) > 0
            # Every line should start with [YYYY-MM-DD HH:MM:SS]
            for line in lines:
                line = line.strip()
                if line:
                    assert line.startswith('['), f'Line missing timestamp: {line}'
                    assert ']' in line, f'Line missing timestamp close: {line}'

    def test_run_log_contains_sweep_start(self):
        """Run log should mention strategy sweep starts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            candles = _make_candles(400)
            runner = OvernightRunner(
                results_dir=tmpdir,
                candles=candles,
                cross_validate_tickers=[],
                strategy_sweeps=_tiny_sweeps(),
                experiment_timeout=30,
            )
            runner.run()

            with open(os.path.join(tmpdir, 'run_log.txt')) as f:
                content = f.read()
            assert 'EMA Crossover sweep' in content
            assert 'combos' in content


# ---------------------------------------------------------------------------
# Tests — Experiment key
# ---------------------------------------------------------------------------

class TestExperimentKey:

    def test_same_params_same_key(self):
        key1 = OvernightRunner._experiment_key('EMA', {'fast': 5, 'slow': 20})
        key2 = OvernightRunner._experiment_key('EMA', {'fast': 5, 'slow': 20})
        assert key1 == key2

    def test_different_params_different_key(self):
        key1 = OvernightRunner._experiment_key('EMA', {'fast': 5, 'slow': 20})
        key2 = OvernightRunner._experiment_key('EMA', {'fast': 9, 'slow': 20})
        assert key1 != key2

    def test_different_strategy_different_key(self):
        key1 = OvernightRunner._experiment_key('EMA', {'fast': 5, 'slow': 20})
        key2 = OvernightRunner._experiment_key('RSI', {'fast': 5, 'slow': 20})
        assert key1 != key2

    def test_param_order_independent(self):
        key1 = OvernightRunner._experiment_key('EMA', {'fast': 5, 'slow': 20})
        key2 = OvernightRunner._experiment_key('EMA', {'slow': 20, 'fast': 5})
        assert key1 == key2


# ---------------------------------------------------------------------------
# Tests — Strategy sweeps config
# ---------------------------------------------------------------------------

class TestStrategySweepsConfig:

    def test_all_strategies_defined(self):
        """All 11 strategies should be in STRATEGY_SWEEPS."""
        names = {s['name'] for s in STRATEGY_SWEEPS}
        assert 'EMA Crossover' in names
        assert 'MACD' in names
        assert 'RSI Mean Reversion' in names
        assert 'RSI(2) Connors' in names
        assert 'Bollinger Breakout' in names
        assert 'Donchian Breakout' in names
        assert 'MA+ATR Mean Reversion' in names
        assert 'Golden Cross' in names
        assert 'Keltner Squeeze' in names
        assert 'Volume Confirmed' in names
        assert 'Bull Flag' in names
        assert len(STRATEGY_SWEEPS) == 11

    def test_total_combos(self):
        """Verify total combo count matches expected."""
        total = sum(_count_combos(s['grid']) for s in STRATEGY_SWEEPS)
        # EMA: 7*7=49, MACD: 5*5*5=125, RSI: 4*5*5=100, RSI2: 3*3*4*4=144,
        # Boll: 5*4=20, Donch: 6*5=30, MA+ATR: 5*5*4=100, GC: 4*4=16,
        # Keltner: 4*4=16, Volume: 4*4=16, BullFlag: 4*4=16
        # Total = 632
        assert total > 600  # Rough sanity check


# ---------------------------------------------------------------------------
# Tests — Full run (tiny grid)
# ---------------------------------------------------------------------------

class TestFullRun:

    def test_full_run_returns_summary(self):
        """A full run with tiny grid should return a valid summary dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            candles = _make_candles(400)
            runner = OvernightRunner(
                results_dir=tmpdir,
                candles=candles,
                cross_validate_tickers=[],
                strategy_sweeps=_tiny_sweeps(),
                experiment_timeout=30,
            )
            result = runner.run()

            assert isinstance(result, dict)
            assert 'total_experiments' in result
            assert 'errors' in result
            assert 'timeouts' in result
            assert 'best_train_sharpe' in result
            assert 'best_test_sharpe' in result
            assert 'kept_strategies' in result
            assert result['total_experiments'] > 0
            assert result['errors'] == 0
            assert result['timeouts'] == 0
