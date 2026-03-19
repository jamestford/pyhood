"""Tests for the autoresearch research memory system."""

from __future__ import annotations

from pyhood.autoresearch.memory import ResearchMemory
from pyhood.autoresearch.models import ExperimentResult
from pyhood.backtest.models import BacktestResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_backtest(
    sharpe: float = 1.0,
    total_return: float = 10.0,
    total_trades: int = 30,
    max_drawdown: float = -5.0,
    win_rate: float = 55.0,
    profit_factor: float = 1.5,
    name: str = 'Test',
    regime_breakdown: dict = None,
) -> BacktestResult:
    """Create a minimal BacktestResult for testing."""
    return BacktestResult(
        strategy_name=name,
        symbol='TEST',
        period='2020-01-01 to 2025-01-01',
        total_return=total_return,
        annual_return=total_return / 5,
        sharpe_ratio=sharpe,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        profit_factor=profit_factor,
        total_trades=total_trades,
        avg_trade_return=total_return / max(total_trades, 1),
        avg_win=1.0,
        avg_loss=-0.5,
        buy_hold_return=8.0,
        alpha=total_return - 8.0,
        trades=[],
        equity_curve=[10000],
        regime_breakdown=regime_breakdown,
    )


def _make_experiment(
    strategy_name: str = 'EMA (fast=5, slow=20)',
    params: dict = None,
    train_sharpe: float = 1.2,
    test_sharpe: float = 0.9,
    kept: bool = True,
    reason: str = 'KEPT',
    regime_breakdown: dict = None,
    cross_validation: dict = None,
    validate_sharpe: float = None,
) -> ExperimentResult:
    """Create a minimal ExperimentResult for testing."""
    if params is None:
        params = {'fast': 5, 'slow': 20}

    train = _make_backtest(
        sharpe=train_sharpe, name=strategy_name,
        regime_breakdown=regime_breakdown,
    )
    test = (
        _make_backtest(sharpe=test_sharpe, name=strategy_name)
        if test_sharpe is not None else None
    )
    validate = (
        _make_backtest(sharpe=validate_sharpe, name=strategy_name)
        if validate_sharpe is not None else None
    )

    return ExperimentResult(
        experiment_id=1,
        strategy_code=f'ema_crossover(**{params})',
        strategy_name=strategy_name,
        params=params,
        train_result=train,
        test_result=test,
        validate_result=validate,
        kept=kept,
        reason=reason,
        timestamp='2025-01-01T00:00:00Z',
        cross_validation=cross_validation,
    )


# ---------------------------------------------------------------------------
# Tests — Initialization
# ---------------------------------------------------------------------------

class TestInit:

    def test_creates_tables(self):
        mem = ResearchMemory(':memory:')
        # Verify tables exist by querying them
        tables = mem.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {row['name'] for row in tables}
        assert 'experiments' in table_names
        assert 'insights' in table_names
        assert 'priorities' in table_names
        assert 'runs' in table_names
        mem.close()

    def test_idempotent_init(self):
        """Creating ResearchMemory twice on same db doesn't error."""
        mem = ResearchMemory(':memory:')
        mem._create_tables()  # should not raise
        mem.close()


# ---------------------------------------------------------------------------
# Tests — Experiment Storage
# ---------------------------------------------------------------------------

class TestExperimentStorage:

    def test_store_and_query(self):
        mem = ResearchMemory(':memory:')
        exp = _make_experiment()
        run_id = mem.start_run('SPY')
        exp_id = mem.store_experiment(exp, run_id, 'SPY')

        assert exp_id >= 1

        results = mem.get_experiments(ticker='SPY')
        assert len(results) == 1
        assert results[0]['ticker'] == 'SPY'
        assert results[0]['train_sharpe'] == 1.2
        assert results[0]['test_sharpe'] == 0.9
        assert results[0]['kept'] == 1
        mem.close()

    def test_store_multiple(self):
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')
        exps = [
            _make_experiment(strategy_name='A', params={'a': 1}),
            _make_experiment(strategy_name='B', params={'b': 2}),
        ]
        ids = mem.store_experiments(exps, run_id, 'SPY')
        assert len(ids) == 2
        assert ids[0] != ids[1]
        mem.close()

    def test_experiment_exists_dedup(self):
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')
        exp = _make_experiment(strategy_name='EMA', params={'fast': 5, 'slow': 20})
        mem.store_experiment(exp, run_id, 'SPY')

        assert mem.experiment_exists('SPY', 'EMA', {'fast': 5, 'slow': 20})
        assert not mem.experiment_exists('SPY', 'EMA', {'fast': 7, 'slow': 20})
        assert not mem.experiment_exists('QQQ', 'EMA', {'fast': 5, 'slow': 20})
        mem.close()

    def test_query_filters(self):
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')
        mem.store_experiment(
            _make_experiment(strategy_name='EMA (fast=5)', test_sharpe=1.5, kept=True),
            run_id, 'SPY',
        )
        mem.store_experiment(
            _make_experiment(strategy_name='RSI (period=14)', test_sharpe=0.3, kept=False),
            run_id, 'SPY',
        )

        # Filter by min_test_sharpe
        results = mem.get_experiments(min_test_sharpe=1.0)
        assert len(results) == 1

        # Filter by kept_only
        results = mem.get_experiments(kept_only=True)
        assert len(results) == 1
        assert 'EMA' in results[0]['strategy_name']
        mem.close()

    def test_overfit_flagging(self):
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')
        # Train=2.0, test=0.5 → gap = 75% → should be flagged
        exp = _make_experiment(train_sharpe=2.0, test_sharpe=0.5)
        mem.store_experiment(exp, run_id, 'SPY')

        results = mem.get_experiments()
        assert results[0]['overfit_flagged'] == 1
        assert results[0]['overfit_gap'] > 0.5
        mem.close()

    def test_no_test_result(self):
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')
        exp = _make_experiment(test_sharpe=None, kept=False)
        mem.store_experiment(exp, run_id, 'SPY')

        results = mem.get_experiments()
        assert len(results) == 1
        assert results[0]['test_sharpe'] is None
        mem.close()


# ---------------------------------------------------------------------------
# Tests — Run Tracking
# ---------------------------------------------------------------------------

class TestRunTracking:

    def test_start_and_end_run(self):
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')
        assert run_id >= 1

        runs = mem.get_runs()
        assert len(runs) == 1
        assert runs[0]['status'] == 'running'
        assert runs[0]['ticker'] == 'SPY'

        mem.end_run(run_id, status='completed')
        runs = mem.get_runs()
        assert runs[0]['status'] == 'completed'
        assert runs[0]['end_time'] is not None
        mem.close()

    def test_run_stats_populated(self):
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')
        mem.store_experiment(
            _make_experiment(test_sharpe=1.5, kept=True),
            run_id, 'SPY',
        )
        mem.store_experiment(
            _make_experiment(strategy_name='B', params={'b': 1}, test_sharpe=0.3, kept=False),
            run_id, 'SPY',
        )
        mem.end_run(run_id)

        runs = mem.get_runs()
        assert runs[0]['total_experiments'] == 2
        assert runs[0]['kept_count'] == 1
        assert runs[0]['best_sharpe'] == 1.5
        mem.close()

    def test_multiple_runs(self):
        mem = ResearchMemory(':memory:')
        r1 = mem.start_run('SPY')
        r2 = mem.start_run('QQQ')
        assert r1 != r2
        runs = mem.get_runs()
        assert len(runs) == 2
        mem.close()


# ---------------------------------------------------------------------------
# Tests — Insight Generation
# ---------------------------------------------------------------------------

class TestInsightGeneration:

    def test_strategy_failure_insight(self):
        """Strategy failing across 3+ tickers should generate failure insight."""
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('MULTI')

        # Same strategy, low test sharpe across 3 tickers
        for ticker in ['SPY', 'QQQ', 'DIA']:
            for i in range(2):
                mem.store_experiment(
                    _make_experiment(
                        strategy_name=f'BadStrategy (p={i})',
                        params={'p': i},
                        test_sharpe=0.1,
                        kept=False,
                    ),
                    run_id, ticker,
                )

        insights = mem.generate_insights()
        failure_insights = [i for i in insights if 'fails' in i['insight_text']]
        assert len(failure_insights) >= 1
        assert 'BadStrategy' in failure_insights[0]['insight_text']
        mem.close()

    def test_overfitting_insight(self):
        """Overfitted experiments should generate overfitting insights."""
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')

        # Train=3.0, test=0.5 → 83% gap → overfitted
        mem.store_experiment(
            _make_experiment(
                strategy_name='OverfitStrat (x=1)',
                params={'x': 1},
                train_sharpe=3.0,
                test_sharpe=0.5,
            ),
            run_id, 'SPY',
        )

        insights = mem.generate_insights()
        overfit_insights = [i for i in insights if i['category'] == 'overfitting']
        assert len(overfit_insights) >= 1
        assert 'overfitted' in overfit_insights[0]['insight_text'].lower()
        assert overfit_insights[0]['confidence'] == 'high'
        mem.close()

    def test_regime_dependency_insight(self):
        """Strategy with 80%+ P&L from one regime should generate insight."""
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')

        regime_breakdown = {
            'bull': {'total_pnl': 900, 'trades': 10},
            'bear': {'total_pnl': 50, 'trades': 5},
            'recovery': {'total_pnl': 50, 'trades': 3},
        }
        mem.store_experiment(
            _make_experiment(
                strategy_name='RegimeStrat (k=1)',
                params={'k': 1},
                regime_breakdown=regime_breakdown,
            ),
            run_id, 'SPY',
        )

        insights = mem.generate_insights()
        regime_insights = [i for i in insights if i['category'] == 'regime']
        assert len(regime_insights) >= 1
        assert 'regime-dependent' in regime_insights[0]['insight_text']
        mem.close()

    def test_confidence_levels(self):
        """Verify confidence levels are correctly assigned."""
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')

        # Strategy family with 5+ overfit experiments → high confidence
        for i in range(6):
            mem.store_experiment(
                _make_experiment(
                    strategy_name=f'BadFamily (p={i})',
                    params={'p': i},
                    train_sharpe=3.0,
                    test_sharpe=0.3,
                ),
                run_id, 'SPY',
            )

        insights = mem.generate_insights()
        family_insights = [
            i for i in insights
            if 'family tends to overfit' in i.get('insight_text', '')
        ]
        if family_insights:
            assert family_insights[0]['confidence'] == 'high'
        mem.close()

    def test_no_insights_when_empty(self):
        mem = ResearchMemory(':memory:')
        insights = mem.generate_insights()
        assert insights == []
        mem.close()

    def test_promise_insight(self):
        """Strategy with high test Sharpe should generate promise insight."""
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')
        mem.store_experiment(
            _make_experiment(
                strategy_name='GoodStrat (x=1)',
                params={'x': 1},
                test_sharpe=1.5,
                kept=True,
            ),
            run_id, 'SPY',
        )

        insights = mem.generate_insights()
        promise = [i for i in insights if 'promise' in i.get('insight_text', '')]
        assert len(promise) >= 1
        mem.close()


# ---------------------------------------------------------------------------
# Tests — Get/Invalidate Insights
# ---------------------------------------------------------------------------

class TestInsightManagement:

    def test_get_insights_with_filters(self):
        mem = ResearchMemory(':memory:')
        # Manually insert insights
        mem.conn.execute(
            "INSERT INTO insights (category, insight_text, confidence,"
            " evidence_count) VALUES (?, ?, ?, ?)",
            ('overfitting', 'Test overfit', 'high', 3),
        )
        mem.conn.execute(
            "INSERT INTO insights (category, insight_text, confidence,"
            " evidence_count) VALUES (?, ?, ?, ?)",
            ('strategy_performance', 'Test perf', 'medium', 2),
        )
        mem.conn.commit()

        # Filter by category
        results = mem.get_insights(category='overfitting')
        assert len(results) == 1
        assert results[0]['category'] == 'overfitting'

        # Filter by confidence
        results = mem.get_insights(confidence='high')
        assert len(results) == 1

        # All valid
        results = mem.get_insights()
        assert len(results) == 2
        mem.close()

    def test_invalidate_insight(self):
        mem = ResearchMemory(':memory:')
        mem.conn.execute(
            "INSERT INTO insights (category, insight_text, confidence,"
            " evidence_count) VALUES (?, ?, ?, ?)",
            ('overfitting', 'Test insight', 'high', 1),
        )
        mem.conn.commit()

        insights = mem.get_insights()
        assert len(insights) == 1
        insight_id = insights[0]['id']

        mem.invalidate_insight(insight_id, "No longer relevant")

        # Should not appear in valid_only=True query
        valid = mem.get_insights(valid_only=True)
        assert len(valid) == 0

        # Should appear in valid_only=False query
        all_insights = mem.get_insights(valid_only=False)
        assert len(all_insights) == 1
        assert all_insights[0]['still_valid'] == 0
        assert all_insights[0]['invalidated_reason'] == "No longer relevant"
        mem.close()


# ---------------------------------------------------------------------------
# Tests — Priority Generation
# ---------------------------------------------------------------------------

class TestPriorityGeneration:

    def test_generate_priorities_from_insights(self):
        mem = ResearchMemory(':memory:')
        # Insert a "shows promise" insight
        mem.conn.execute(
            "INSERT INTO insights (category, insight_text, confidence,"
            " evidence_count, still_valid) VALUES (?, ?, ?, ?, ?)",
            (
                'strategy_performance',
                'EMA shows promise on SPY (best test Sharpe: 1.20)',
                'medium', 3, 1,
            ),
        )
        mem.conn.commit()

        priorities = mem.generate_priorities()
        assert len(priorities) >= 1
        assert priorities[0]['priority_level'] == 'high'
        assert 'promise' in priorities[0]['description'].lower()
        mem.close()

    def test_no_duplicate_priorities(self):
        mem = ResearchMemory(':memory:')
        mem.conn.execute(
            "INSERT INTO insights (category, insight_text, confidence,"
            " evidence_count, still_valid) VALUES (?, ?, ?, ?, ?)",
            ('strategy_performance', 'EMA shows promise on SPY', 'medium', 3, 1),
        )
        mem.conn.commit()

        p1 = mem.generate_priorities()
        p2 = mem.generate_priorities()
        assert len(p1) >= 1
        assert len(p2) == 0  # Duplicates not created
        mem.close()

    def test_get_priorities_ordering(self):
        mem = ResearchMemory(':memory:')
        mem.conn.execute(
            "INSERT INTO priorities (description, priority_level, status) VALUES (?, ?, ?)",
            ('Low pri', 'low', 'pending'),
        )
        mem.conn.execute(
            "INSERT INTO priorities (description, priority_level, status) VALUES (?, ?, ?)",
            ('High pri', 'high', 'pending'),
        )
        mem.conn.execute(
            "INSERT INTO priorities (description, priority_level, status) VALUES (?, ?, ?)",
            ('Med pri', 'medium', 'pending'),
        )
        mem.conn.commit()

        priorities = mem.get_priorities()
        assert len(priorities) == 3
        assert priorities[0]['priority_level'] == 'high'
        assert priorities[1]['priority_level'] == 'medium'
        assert priorities[2]['priority_level'] == 'low'
        mem.close()

    def test_update_priority(self):
        mem = ResearchMemory(':memory:')
        mem.conn.execute(
            "INSERT INTO priorities (description, priority_level, status) VALUES (?, ?, ?)",
            ('Test', 'high', 'pending'),
        )
        mem.conn.commit()

        priorities = mem.get_priorities()
        pid = priorities[0]['id']

        mem.update_priority(pid, 'completed', result_experiment_id=42)

        # Should no longer be pending
        pending = mem.get_priorities(status='pending')
        assert len(pending) == 0

        completed = mem.get_priorities(status='completed')
        assert len(completed) == 1
        assert completed[0]['result_experiment_id'] == 42
        assert completed[0]['completed_date'] is not None
        mem.close()


# ---------------------------------------------------------------------------
# Tests — Should Skip
# ---------------------------------------------------------------------------

class TestShouldSkip:

    def test_skip_existing_experiment(self):
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')
        mem.store_experiment(
            _make_experiment(strategy_name='EMA', params={'fast': 5}),
            run_id, 'SPY',
        )

        skip, reason = mem.should_skip('SPY', 'EMA', {'fast': 5})
        assert skip is True
        assert 'dedupe' in reason.lower()
        mem.close()

    def test_skip_based_on_failure_insight(self):
        mem = ResearchMemory(':memory:')
        # Insert a high-confidence failure insight
        mem.conn.execute(
            "INSERT INTO insights (category, insight_text, confidence,"
            " evidence_count, still_valid) VALUES (?, ?, ?, ?, ?)",
            (
                'strategy_performance',
                'BadStrat consistently fails across tickers: SPY, QQQ, DIA',
                'high', 10, 1,
            ),
        )
        mem.conn.commit()

        skip, reason = mem.should_skip('SPY', 'BadStrat (x=1)', {'x': 1})
        assert skip is True
        assert 'insight' in reason.lower()
        mem.close()

    def test_no_skip_for_new_experiment(self):
        mem = ResearchMemory(':memory:')
        skip, reason = mem.should_skip('SPY', 'NewStrat', {'x': 1})
        assert skip is False
        assert reason == ''
        mem.close()


# ---------------------------------------------------------------------------
# Tests — Suggested Experiments
# ---------------------------------------------------------------------------

class TestSuggestedExperiments:

    def test_ordering(self):
        mem = ResearchMemory(':memory:')
        mem.conn.execute(
            "INSERT INTO priorities (description, priority_level, status) VALUES (?, ?, ?)",
            ('Low task', 'low', 'pending'),
        )
        mem.conn.execute(
            "INSERT INTO priorities (description, priority_level, status) VALUES (?, ?, ?)",
            ('High task', 'high', 'pending'),
        )
        mem.conn.commit()

        suggestions = mem.get_suggested_experiments('SPY')
        assert len(suggestions) == 2
        assert suggestions[0]['priority_level'] == 'high'
        assert suggestions[1]['priority_level'] == 'low'
        mem.close()

    def test_limit(self):
        mem = ResearchMemory(':memory:')
        for i in range(10):
            mem.conn.execute(
                "INSERT INTO priorities (description, priority_level, status) VALUES (?, ?, ?)",
                (f'Task {i}', 'medium', 'pending'),
            )
        mem.conn.commit()

        suggestions = mem.get_suggested_experiments('SPY', limit=3)
        assert len(suggestions) == 3
        mem.close()


# ---------------------------------------------------------------------------
# Tests — Run Summary
# ---------------------------------------------------------------------------

class TestRunSummary:

    def test_run_summary_specific(self):
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')
        mem.store_experiment(_make_experiment(), run_id, 'SPY')
        mem.end_run(run_id)

        summary = mem.get_run_summary(run_id)
        assert 'SPY' in summary
        assert 'completed' in summary
        assert 'Run #' in summary
        mem.close()

    def test_run_summary_all(self):
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')
        mem.end_run(run_id)

        summary = mem.get_run_summary()
        assert 'Research Memory Summary' in summary
        assert 'Total runs: 1' in summary
        mem.close()

    def test_run_summary_no_runs(self):
        mem = ResearchMemory(':memory:')
        summary = mem.get_run_summary()
        assert 'No runs recorded' in summary
        mem.close()

    def test_run_summary_missing_id(self):
        mem = ResearchMemory(':memory:')
        summary = mem.get_run_summary(run_id=999)
        assert 'No run found' in summary
        mem.close()


# ---------------------------------------------------------------------------
# Tests — Stats
# ---------------------------------------------------------------------------

class TestStats:

    def test_empty_stats(self):
        mem = ResearchMemory(':memory:')
        s = mem.stats()
        assert s['total_experiments'] == 0
        assert s['total_insights'] == 0
        assert s['total_runs'] == 0
        assert s['pending_priorities'] == 0
        assert s['kept_experiments'] == 0
        assert s['overfit_flagged'] == 0
        assert s['active_insights'] == 0
        mem.close()

    def test_stats_after_operations(self):
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')
        mem.store_experiment(
            _make_experiment(kept=True, train_sharpe=2.0, test_sharpe=0.5),
            run_id, 'SPY',
        )
        mem.store_experiment(
            _make_experiment(
                strategy_name='B', params={'b': 1}, kept=False,
                train_sharpe=0.8, test_sharpe=0.7,
            ),
            run_id, 'SPY',
        )

        s = mem.stats()
        assert s['total_experiments'] == 2
        assert s['total_runs'] == 1
        assert s['kept_experiments'] == 1
        # first: train=2.0, test=0.5 → gap > 50%
        # second: train=0.8, test=0.7 → gap 12.5%
        assert s['overfit_flagged'] == 1
        mem.close()


# ---------------------------------------------------------------------------
# Tests — Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_inf_profit_factor(self):
        """profit_factor=inf should be stored safely."""
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')
        exp = _make_experiment()
        # Manually set profit_factor to inf
        exp.train_result = _make_backtest(profit_factor=float('inf'))
        mem.store_experiment(exp, run_id, 'SPY')
        results = mem.get_experiments()
        assert len(results) == 1
        assert results[0]['train_profit_factor'] == 999999.0
        mem.close()

    def test_empty_params(self):
        """Empty params dict should work."""
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')
        exp = _make_experiment(params={})
        mem.store_experiment(exp, run_id, 'SPY')
        assert mem.experiment_exists('SPY', exp.strategy_name, {})
        mem.close()

    def test_special_characters_in_strategy_name(self):
        mem = ResearchMemory(':memory:')
        run_id = mem.start_run('SPY')
        exp = _make_experiment(strategy_name="EMA (fast=5, slow=20) — test's \"best\"")
        mem.store_experiment(exp, run_id, 'SPY')
        results = mem.get_experiments()
        assert len(results) == 1
        mem.close()
