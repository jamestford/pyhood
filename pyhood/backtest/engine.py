"""Core backtesting engine."""

from __future__ import annotations

import math
from datetime import datetime

from pyhood.backtest.models import BacktestResult, Trade
from pyhood.models import Candle


class Backtester:
    """Backtesting engine for strategy evaluation.

    Takes historical candle data and runs strategy functions against it,
    tracking portfolio performance and generating detailed metrics.

    Usage with pyhood data:
        candles = client.get_stock_historicals("AAPL", span="5year")
        bt = Backtester(candles)

    Usage with yfinance (recommended for backtesting — 30+ years of data):
        bt = Backtester.from_yfinance("AAPL", period="10y")
        bt = Backtester.from_yfinance("GME", start="2019-01-01", end="2021-06-01")
    """

    def __init__(self, candles: list[Candle], initial_capital: float = 10000.0):
        """Initialize with historical candle data.

        Args:
            candles: List of historical price candles
            initial_capital: Starting portfolio value
        """
        if not candles:
            raise ValueError("Cannot backtest with empty candle data")

        # Sort candles by date to ensure chronological order
        self.candles = sorted(candles, key=lambda c: c.begins_at)
        self.initial_capital = initial_capital
        self.symbol = candles[0].symbol

    @classmethod
    def from_yfinance(
        cls,
        symbol: str,
        period: str = "10y",
        start: str | None = None,
        end: str | None = None,
        initial_capital: float = 10000.0,
    ) -> Backtester:
        """Create a Backtester using Yahoo Finance historical data.

        This is the recommended way to create a Backtester for serious
        backtesting — yfinance provides 30+ years of daily data, adjusted
        for splits and dividends, with no API key required.

        Args:
            symbol: Ticker symbol (e.g., 'AAPL', 'GME')
            period: Data period. One of '1d', '5d', '1mo', '3mo', '6mo',
                '1y', '2y', '5y', '10y', 'ytd', 'max'. Default '10y'.
                Ignored if start/end are provided.
            start: Start date string 'YYYY-MM-DD'. Overrides period.
            end: End date string 'YYYY-MM-DD'. Overrides period.
            initial_capital: Starting portfolio value. Default $10,000.

        Returns:
            Backtester instance loaded with historical data.

        Raises:
            ImportError: If yfinance is not installed.
            ValueError: If no data is returned for the symbol.

        Example:
            bt = Backtester.from_yfinance("AAPL", period="10y")
            bt = Backtester.from_yfinance("GME", start="2019-01-01")
            result = bt.run(my_strategy, "My Strategy")
        """
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError(
                "yfinance is required for from_yfinance(). "
                "Install it with: pip install yfinance"
            )

        ticker = yf.Ticker(symbol.upper())

        if start:
            df = ticker.history(start=start, end=end)
        else:
            df = ticker.history(period=period)

        if df.empty:
            raise ValueError(
                f"No historical data returned for {symbol}. "
                f"Check the symbol and date range."
            )

        candles: list[Candle] = []
        for date, row in df.iterrows():
            candles.append(Candle(
                symbol=symbol.upper(),
                begins_at=date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                open_price=float(row["Open"]),
                close_price=float(row["Close"]),
                high_price=float(row["High"]),
                low_price=float(row["Low"]),
                volume=int(row["Volume"]),
            ))

        return cls(candles, initial_capital)

    def run(self, strategy_fn, strategy_name: str = "Strategy") -> BacktestResult:
        """Run a strategy function against the candle data.

        Args:
            strategy_fn: Function that receives (candles_so_far, position) and returns:
                'buy' - enter long
                'sell' - exit long
                'short' - enter short (optional)
                'cover' - exit short (optional)
                None - do nothing
            strategy_name: Name for the strategy

        Returns:
            BacktestResult with performance metrics and trade history
        """
        trades = []
        equity_curve = []

        cash = self.initial_capital
        # {'side': 'long'/'short', 'quantity': float, 'entry_price': float, 'entry_date': str}
        position = None

        for i, candle in enumerate(self.candles):
            # Give strategy all candles up to this point
            candles_so_far = self.candles[:i + 1]

            # Get strategy signal
            signal = strategy_fn(candles_so_far, position)

            # Process signal
            if signal == 'buy' and position is None:
                # Enter long position
                shares = cash / candle.close_price
                position = {
                    'side': 'long',
                    'quantity': shares,
                    'entry_price': candle.close_price,
                    'entry_date': candle.begins_at
                }
                cash = 0.0  # All cash invested

            elif signal == 'sell' and position and position['side'] == 'long':
                # Exit long position
                exit_value = position['quantity'] * candle.close_price
                pnl = exit_value - (position['quantity'] * position['entry_price'])
                pnl_pct = (pnl / (position['quantity'] * position['entry_price'])) * 100

                trade = Trade(
                    entry_date=position['entry_date'],
                    exit_date=candle.begins_at,
                    side=position['side'],
                    entry_price=position['entry_price'],
                    exit_price=candle.close_price,
                    quantity=position['quantity'],
                    pnl=pnl,
                    pnl_pct=pnl_pct
                )
                trades.append(trade)

                cash = exit_value
                position = None

            elif signal == 'short' and position is None:
                # Enter short position
                shares = cash / candle.close_price
                position = {
                    'side': 'short',
                    'quantity': shares,
                    'entry_price': candle.close_price,
                    'entry_date': candle.begins_at
                }
                # For short selling, we assume we receive cash from the sale
                # but we track the liability

            elif signal == 'cover' and position and position['side'] == 'short':
                # Exit short position
                cost_to_cover = position['quantity'] * candle.close_price
                initial_proceeds = position['quantity'] * position['entry_price']
                pnl = initial_proceeds - cost_to_cover
                pnl_pct = (pnl / initial_proceeds) * 100

                trade = Trade(
                    entry_date=position['entry_date'],
                    exit_date=candle.begins_at,
                    side=position['side'],
                    entry_price=position['entry_price'],
                    exit_price=candle.close_price,
                    quantity=position['quantity'],
                    pnl=pnl,
                    pnl_pct=pnl_pct
                )
                trades.append(trade)

                cash = cash - cost_to_cover + initial_proceeds
                position = None

            # Calculate current portfolio value
            if position is None:
                portfolio_value = cash
            elif position['side'] == 'long':
                portfolio_value = position['quantity'] * candle.close_price
            else:  # short position
                # Cash from initial sale minus current cost to cover
                initial_proceeds = position['quantity'] * position['entry_price']
                current_cost = position['quantity'] * candle.close_price
                portfolio_value = cash + initial_proceeds - current_cost

            equity_curve.append(portfolio_value)

        # Calculate metrics
        return self._calculate_metrics(
            strategy_name=strategy_name,
            trades=trades,
            equity_curve=equity_curve
        )

    def _calculate_metrics(
        self, strategy_name: str, trades: list[Trade], equity_curve: list[float]
    ) -> BacktestResult:
        """Calculate all performance metrics for the backtest results."""
        if not equity_curve:
            raise ValueError("Cannot calculate metrics with empty equity curve")

        # Basic returns
        final_value = equity_curve[-1]
        total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100

        # Time period calculation
        start_date = self.candles[0].begins_at
        end_date = self.candles[-1].begins_at
        period = f"{start_date[:10]} to {end_date[:10]}"

        # Annual return (CAGR)
        try:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            years = (end_dt - start_dt).days / 365.25
            if years > 0:
                annual_return = (((final_value / self.initial_capital) ** (1 / years)) - 1) * 100
            else:
                annual_return = 0.0
        except (ValueError, ZeroDivisionError):
            annual_return = 0.0

        # Daily returns for Sharpe ratio
        daily_returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i-1] != 0:
                daily_return = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
                daily_returns.append(daily_return)

        # Sharpe ratio (annualized, risk-free rate = 0)
        if daily_returns:
            mean_daily_return = sum(daily_returns) / len(daily_returns)
            variance = sum((r - mean_daily_return) ** 2 for r in daily_returns) / len(daily_returns)
            daily_std = math.sqrt(variance) if variance > 0 else 0
            if daily_std > 0:
                sharpe_ratio = (mean_daily_return / daily_std) * math.sqrt(252)
            else:
                sharpe_ratio = 0.0
        else:
            sharpe_ratio = 0.0

        # Maximum drawdown
        peak = self.initial_capital
        max_dd = 0.0
        for value in equity_curve:
            if value > peak:
                peak = value
            drawdown = ((value - peak) / peak) * 100
            if drawdown < max_dd:
                max_dd = drawdown

        # Trade statistics
        if trades:
            winning_trades = [t for t in trades if t.pnl > 0]
            losing_trades = [t for t in trades if t.pnl < 0]

            total_trades = len(trades)
            win_rate = (len(winning_trades) / total_trades) * 100

            total_wins = sum(t.pnl for t in winning_trades)
            total_losses = abs(sum(t.pnl for t in losing_trades))
            profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')

            avg_trade_return = sum(t.pnl_pct for t in trades) / total_trades
            if winning_trades:
                avg_win = sum(t.pnl_pct for t in winning_trades) / len(winning_trades)
            else:
                avg_win = 0.0
            if losing_trades:
                avg_loss = sum(t.pnl_pct for t in losing_trades) / len(losing_trades)
            else:
                avg_loss = 0.0
        else:
            total_trades = 0
            win_rate = 0.0
            profit_factor = 0.0
            avg_trade_return = 0.0
            avg_win = 0.0
            avg_loss = 0.0

        # Buy and hold benchmark
        first_price = self.candles[0].close_price
        last_price = self.candles[-1].close_price
        buy_hold_return = ((last_price - first_price) / first_price) * 100

        # Alpha (excess return vs buy and hold)
        alpha = total_return - buy_hold_return

        return BacktestResult(
            strategy_name=strategy_name,
            symbol=self.symbol,
            period=period,
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_dd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            avg_trade_return=avg_trade_return,
            avg_win=avg_win,
            avg_loss=avg_loss,
            buy_hold_return=buy_hold_return,
            alpha=alpha,
            trades=trades,
            equity_curve=equity_curve
        )
