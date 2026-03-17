"""Utilities for comparing multiple backtest results."""

from __future__ import annotations

from pyhood.backtest.models import BacktestResult


def compare_backtests(results: list[BacktestResult]) -> str:
    """Format comparison table of multiple backtest results.

    Args:
        results: List of BacktestResult objects to compare

    Returns:
        Formatted string table comparing the strategies
    """
    if not results:
        return "No backtest results to compare."

    # Column headers
    headers = [
        "Strategy", "Symbol", "Period", "Total Return (%)", "Annual Return (%)",
        "Sharpe Ratio", "Max DD (%)", "Win Rate (%)", "Profit Factor",
        "Total Trades", "Alpha (%)"
    ]

    # Build rows
    rows = []
    for result in results:
        row = [
            result.strategy_name,
            result.symbol,
            result.period,
            f"{result.total_return:.2f}",
            f"{result.annual_return:.2f}",
            f"{result.sharpe_ratio:.2f}",
            f"{result.max_drawdown:.2f}",
            f"{result.win_rate:.2f}",
            f"{result.profit_factor:.2f}" if result.profit_factor != float('inf') else "∞",
            str(result.total_trades),
            f"{result.alpha:.2f}"
        ]
        rows.append(row)

    # Calculate column widths
    col_widths = []
    for i in range(len(headers)):
        max_width = len(headers[i])
        for row in rows:
            max_width = max(max_width, len(row[i]))
        col_widths.append(max_width + 2)  # Add padding

    # Format table
    lines = []

    # Header
    header_line = "|".join(header.ljust(col_widths[i]) for i, header in enumerate(headers))
    lines.append(header_line)

    # Separator
    separator = "|".join("-" * col_widths[i] for i in range(len(headers)))
    lines.append(separator)

    # Data rows
    for row in rows:
        row_line = "|".join(row[i].ljust(col_widths[i]) for i in range(len(row)))
        lines.append(row_line)

    return "\n".join(lines)


def rank_backtests(results: list[BacktestResult], by: str = "sharpe_ratio") -> list[BacktestResult]:
    """Sort results by a metric.

    Args:
        results: List of BacktestResult objects
        by: Metric to sort by. Options:
            - "total_return"
            - "annual_return"
            - "sharpe_ratio" (default)
            - "max_drawdown" (sorts by least negative)
            - "win_rate"
            - "profit_factor"
            - "alpha"

    Returns:
        Sorted list of BacktestResult objects (best first)
    """
    if not results:
        return results

    # Define sorting key and reverse flag for each metric
    sort_configs = {
        "total_return": (lambda r: r.total_return, True),
        "annual_return": (lambda r: r.annual_return, True),
        "sharpe_ratio": (lambda r: r.sharpe_ratio, True),
        "max_drawdown": (lambda r: r.max_drawdown, True),  # Less negative is better
        "win_rate": (lambda r: r.win_rate, True),
        "profit_factor": (
            lambda r: r.profit_factor if r.profit_factor != float('inf') else 999999,
            True
        ),
        "alpha": (lambda r: r.alpha, True)
    }

    if by not in sort_configs:
        raise ValueError(f"Unknown ranking metric: {by}. Available: {list(sort_configs.keys())}")

    key_fn, reverse = sort_configs[by]
    return sorted(results, key=key_fn, reverse=reverse)
