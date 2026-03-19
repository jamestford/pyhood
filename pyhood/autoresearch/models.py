"""Data models for autoresearch experiments."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyhood.backtest.models import BacktestResult


@dataclass
class ExperimentResult:
    """Result of a single autoresearch experiment."""
    experiment_id: int
    strategy_code: str              # The Python code of the strategy function
    strategy_name: str
    params: dict                    # Parameters used
    train_result: BacktestResult
    test_result: BacktestResult | None = None
    validate_result: BacktestResult | None = None
    kept: bool = False              # Whether this beat the previous best
    reason: str = ''                # Why kept/discarded
    timestamp: str = ''
    cross_validation: dict | None = None  # Results from cross_validate()


@dataclass
class ExperimentLog:
    """Full log of all experiments in an autoresearch run."""
    experiments: list[ExperimentResult] = field(default_factory=list)
    best_train_sharpe: float = 0.0
    best_test_sharpe: float = 0.0
    ticker: str = ''
    total_experiments: int = 0
