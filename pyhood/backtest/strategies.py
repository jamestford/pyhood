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


def _calculate_sma(prices: list[float], period: int) -> list[float]:
    """Calculate Simple Moving Average.

    Args:
        prices: List of prices
        period: SMA period

    Returns:
        List of SMA values (None for insufficient data)
    """
    if not prices or period <= 0:
        return []

    sma_values = []
    for i in range(len(prices)):
        if i < period - 1:
            sma_values.append(None)
        else:
            sma_values.append(sum(prices[i - period + 1:i + 1]) / period)

    return sma_values


def _calculate_atr(candles: list, period: int = 14) -> list[float]:
    """Calculate Average True Range.

    Args:
        candles: List of Candle objects with high_price, low_price, close_price
        period: ATR period

    Returns:
        List of ATR values (None for insufficient data)
    """
    if len(candles) < 2:
        return [None] * len(candles)

    # Calculate True Range for each bar
    true_ranges = [None]  # First bar has no previous close
    for i in range(1, len(candles)):
        high = candles[i].high_price
        low = candles[i].low_price
        prev_close = candles[i - 1].close_price

        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)

    # Calculate ATR as SMA of True Range
    atr_values = []
    for i in range(len(true_ranges)):
        if i < period:
            atr_values.append(None)
        else:
            valid_trs = [tr for tr in true_ranges[i - period + 1:i + 1] if tr is not None]
            if len(valid_trs) == period:
                atr_values.append(sum(valid_trs) / period)
            else:
                atr_values.append(None)

    return atr_values


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


def ma_atr_mean_reversion(
    ma_period: int = 40,
    atr_length: int = 14,
    mean_period: int = 5,
    entry_multiplier: float = 1.0,
    exit_multiplier: float = 0.5,
) -> Callable:
    """MA + ATR Mean Reversion Strategy (Triple Nested MA + ATR Bands).

    Based on Liran Nachman's QQQ Swing Trading Strategy. Uses triple nested
    moving averages to confirm uptrend, then buys pullbacks using ATR-scaled
    bands around a short-term mean. Exits when price bounces back above mean.

    Trend filter (triple nested MAs):
        MA1 = SMA(close, ma_period)
        MA2 = SMA(MA1, ma_period)
        MA3 = SMA(MA2, ma_period)
        Uptrend = MA1 > MA2 AND MA2 > MA3 AND close > MA3

    Entry: uptrend AND close < mean - entry_multiplier * ATR
    Exit: close > mean + exit_multiplier * ATR

    Source: https://lirannh.medium.com/forget-50-indicators-this-3-line-qqq-strategy-beats-90-of-traders-85eb3edbddc2

    Args:
        ma_period: SMA period for triple nested MAs (default 40)
        atr_length: ATR period (default 14)
        mean_period: Short-term mean period (default 5)
        entry_multiplier: ATR multiplier for entry band (default 1.0)
        exit_multiplier: ATR multiplier for exit band (default 0.5)

    Returns:
        Strategy function compatible with Backtester.run()
    """
    # Need 3x ma_period for triple nesting (MA3 needs 3*ma_period - 2 bars)
    min_bars = max(3 * ma_period, atr_length, mean_period) + 1

    def strategy_fn(candles: list[Candle], position: dict | None) -> str | None:
        if len(candles) < min_bars:
            return None

        prices = [c.close_price for c in candles]

        # Triple Nested Moving Averages
        ma1 = _calculate_sma(prices, ma_period)
        if ma1[-1] is None:
            return None
        ma2 = _calculate_sma(
            [v if v is not None else 0.0 for v in ma1], ma_period
        )
        if ma2[-1] is None:
            return None
        ma3 = _calculate_sma(
            [v if v is not None else 0.0 for v in ma2], ma_period
        )
        if ma3[-1] is None:
            return None

        # ATR
        atr_values = _calculate_atr(candles, atr_length)
        if atr_values[-1] is None:
            return None

        # Short-term mean
        if len(prices) < mean_period:
            return None
        mean_now = sum(prices[-mean_period:]) / mean_period

        current_price = prices[-1]
        atr_now = atr_values[-1]

        # Trend determination
        uptrend = (ma1[-1] > ma2[-1] and ma2[-1] > ma3[-1]
                   and current_price > ma3[-1])

        # Entry: uptrend AND close < mean - entry_multiplier * ATR
        entry_level = mean_now - (entry_multiplier * atr_now)
        if uptrend and current_price < entry_level and position is None:
            return 'buy'

        # Exit: close > mean + exit_multiplier * ATR
        exit_level = mean_now + (exit_multiplier * atr_now)
        if current_price > exit_level and position and position['side'] == 'long':
            return 'sell'

        return None

    return strategy_fn
