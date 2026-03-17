"""Built-in trading strategies with technical indicators.

All technical indicators are implemented using pure Python without
external dependencies like pandas or ta-lib.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from pyhood.models import Candle


def _calculate_ema(prices: list[float], period: int) -> list[float]:
    """Calculate Exponential Moving Average.

    Args:
        prices: List of prices
        period: EMA period

    Returns:
        List of EMA values (same length as prices, starts with NaN/None for insufficient data)
    """
    if not prices or period <= 0:
        return []

    ema_values = []
    multiplier = 2.0 / (period + 1)

    # First EMA value is simple average of first 'period' prices
    for i in range(len(prices)):
        if i < period - 1:
            ema_values.append(None)
        elif i == period - 1:
            # First EMA is SMA
            sma = sum(prices[:period]) / period
            ema_values.append(sma)
        else:
            # EMA = (Close - EMA_prev) * multiplier + EMA_prev
            ema_prev = ema_values[-1]
            ema = (prices[i] - ema_prev) * multiplier + ema_prev
            ema_values.append(ema)

    return ema_values


def _calculate_rsi(prices: list[float], period: int = 14) -> list[float]:
    """Calculate Relative Strength Index.

    Args:
        prices: List of closing prices
        period: RSI period (default 14)

    Returns:
        List of RSI values
    """
    if len(prices) < period + 1:
        return [None] * len(prices)

    rsi_values = []

    # Calculate price changes
    price_changes = []
    for i in range(1, len(prices)):
        price_changes.append(prices[i] - prices[i-1])

    for i in range(len(prices)):
        if i < period:
            rsi_values.append(None)
        else:
            # Get the last 'period' price changes
            recent_changes = price_changes[i-period:i]

            gains = [change for change in recent_changes if change > 0]
            losses = [abs(change) for change in recent_changes if change < 0]

            avg_gain = sum(gains) / period if gains else 0
            avg_loss = sum(losses) / period if losses else 0

            if avg_loss == 0:
                rsi = 100
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))

            rsi_values.append(rsi)

    return rsi_values


def _calculate_bollinger_bands(
    prices: list[float], period: int = 20, std_dev: float = 2.0
) -> tuple[list[float], list[float], list[float]]:
    """Calculate Bollinger Bands.

    Args:
        prices: List of closing prices
        period: Moving average period
        std_dev: Standard deviation multiplier

    Returns:
        Tuple of (upper_band, middle_band/SMA, lower_band)
    """
    if len(prices) < period:
        return ([None] * len(prices), [None] * len(prices), [None] * len(prices))

    upper_band = []
    middle_band = []  # SMA
    lower_band = []

    for i in range(len(prices)):
        if i < period - 1:
            upper_band.append(None)
            middle_band.append(None)
            lower_band.append(None)
        else:
            # Calculate SMA
            recent_prices = prices[i-period+1:i+1]
            sma = sum(recent_prices) / period

            # Calculate standard deviation
            variance = sum((p - sma) ** 2 for p in recent_prices) / period
            std = math.sqrt(variance)

            upper_band.append(sma + (std_dev * std))
            middle_band.append(sma)
            lower_band.append(sma - (std_dev * std))

    return upper_band, middle_band, lower_band


def ema_crossover(fast: int = 9, slow: int = 21) -> Callable:
    """EMA Crossover Strategy.

    Buy when fast EMA crosses above slow EMA.
    Sell when fast EMA crosses below slow EMA.

    Args:
        fast: Fast EMA period
        slow: Slow EMA period

    Returns:
        Strategy function compatible with Backtester.run()
    """
    def strategy_fn(candles: list[Candle], position: dict | None) -> str | None:
        if len(candles) < slow + 1:
            return None

        prices = [c.close_price for c in candles]
        fast_ema = _calculate_ema(prices, fast)
        slow_ema = _calculate_ema(prices, slow)

        # Need at least 2 values to detect crossover
        if len(fast_ema) < 2 or fast_ema[-1] is None or fast_ema[-2] is None:
            return None
        if slow_ema[-1] is None or slow_ema[-2] is None:
            return None

        # Current and previous values
        fast_now, fast_prev = fast_ema[-1], fast_ema[-2]
        slow_now, slow_prev = slow_ema[-1], slow_ema[-2]

        # Buy signal: fast crosses above slow
        if fast_prev <= slow_prev and fast_now > slow_now and position is None:
            return 'buy'

        # Sell signal: fast crosses below slow
        if (fast_prev >= slow_prev and fast_now < slow_now and
                position and position['side'] == 'long'):
            return 'sell'

        return None

    return strategy_fn


def rsi_mean_reversion(period: int = 14, oversold: float = 30, overbought: float = 70) -> Callable:
    """RSI Mean Reversion Strategy.

    Buy when RSI < oversold threshold.
    Sell when RSI > overbought threshold.

    Args:
        period: RSI calculation period
        oversold: RSI level considered oversold (buy signal)
        overbought: RSI level considered overbought (sell signal)

    Returns:
        Strategy function compatible with Backtester.run()
    """
    def strategy_fn(candles: list[Candle], position: dict | None) -> str | None:
        if len(candles) < period + 1:
            return None

        prices = [c.close_price for c in candles]
        rsi_values = _calculate_rsi(prices, period)

        if not rsi_values or rsi_values[-1] is None:
            return None

        current_rsi = rsi_values[-1]

        # Buy when oversold and no position
        if current_rsi < oversold and position is None:
            return 'buy'

        # Sell when overbought and holding long
        if current_rsi > overbought and position and position['side'] == 'long':
            return 'sell'

        return None

    return strategy_fn


def bollinger_breakout(period: int = 20, std_dev: float = 2.0) -> Callable:
    """Bollinger Bands Breakout Strategy.

    Buy when price closes above upper band (breakout).
    Sell when price closes below middle band (SMA).

    Args:
        period: Bollinger bands period
        std_dev: Standard deviation multiplier

    Returns:
        Strategy function compatible with Backtester.run()
    """
    def strategy_fn(candles: list[Candle], position: dict | None) -> str | None:
        if len(candles) < period:
            return None

        prices = [c.close_price for c in candles]
        upper_band, middle_band, lower_band = _calculate_bollinger_bands(prices, period, std_dev)

        if not upper_band or upper_band[-1] is None or middle_band[-1] is None:
            return None

        current_price = prices[-1]
        upper = upper_band[-1]
        middle = middle_band[-1]

        # Buy signal: price breaks above upper band
        if current_price > upper and position is None:
            return 'buy'

        # Sell signal: price falls below middle band (SMA)
        if current_price < middle and position and position['side'] == 'long':
            return 'sell'

        return None

    return strategy_fn
