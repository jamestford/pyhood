#!/usr/bin/env python3
"""Run overnight autoresearch. Resume-safe — can be restarted safely.

Usage:
    python scripts/run_overnight.py
    python scripts/run_overnight.py --ticker QQQ --period 5y
    python scripts/run_overnight.py --results-dir my_results --timeout 120
"""
import argparse
import os
import sys

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pyhood.autoresearch.overnight import OvernightRunner


def main():
    parser = argparse.ArgumentParser(
        description='Run overnight autoresearch — resume-safe.'
    )
    parser.add_argument('--ticker', default='SPY',
                        help='Ticker symbol (default: SPY)')
    parser.add_argument('--period', default='10y',
                        help='Data period for yfinance (default: 10y)')
    parser.add_argument('--results-dir', default='autoresearch_results',
                        help='Results directory (default: autoresearch_results)')
    parser.add_argument('--timeout', type=int, default=60,
                        help='Per-experiment timeout in seconds (default: 60)')
    parser.add_argument('--slippage', type=float, default=0.01,
                        help='Slippage percentage (default: 0.01)')
    args = parser.parse_args()

    runner = OvernightRunner(
        ticker=args.ticker,
        total_period=args.period,
        results_dir=args.results_dir,
        experiment_timeout=args.timeout,
        slippage_pct=args.slippage,
    )
    result = runner.run()

    print('\n' + '=' * 60)
    print('  OVERNIGHT RUN COMPLETE')
    print('=' * 60)
    for k, v in result.items():
        print(f'  {k}: {v}')
    print('=' * 60)


if __name__ == '__main__':
    main()
