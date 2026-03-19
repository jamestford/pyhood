"""Built-in trading strategies with technical indicators.

All technical indicators are implemented using pure Python without
external dependencies like pandas or ta-lib.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from pyhood.models import Candle


def _classify_regime(candles: list[Candle], index: int, sma_period: int = 200) -> str:
    """Classify market regime at a given candle index.

    Uses the 200-period SMA and its slope to determine regime:
      - bull: price > SMA and SMA rising
      - bear: price < SMA and SMA falling
      - recovery: price > SMA but SMA falling
      - correction: price < SMA but SMA rising
      - unknown: not enough data for SMA calculation

    Args:
        candles: Full list of candles (needs sma_period + 5 bars of context).
        index: Index into candles at which to classify.
        sma_period: SMA period for regime detection (default 200).

    Returns:
        One of 'bull', 'bear', 'recovery', 'correction', 'unknown'.
    """
    # Need at least sma_period bars up to and including index
    if index < sma_period - 1:
        return 'unknown'

    # Also need index - 5 to have a valid SMA for slope comparison
    if index < sma_period - 1 + 5:
        return 'unknown'

    # Calculate SMA at index
    prices_to_index = [c.close_price for c in candles[index - sma_period + 1:index + 1]]
    sma_now = sum(prices_to_index) / sma_period

    # Calculate SMA at index - 5
    prices_to_prev = [c.close_price for c in candles[index - 5 - sma_period + 1:index - 5 + 1]]
    sma_prev = sum(prices_to_prev) / sma_period

    price = candles[index].close_price
    sma_rising = sma_now > sma_prev

    if price > sma_now:
        return 'bull' if sma_rising else 'recovery'
    else:
        return 'correction' if sma_rising else 'bear'


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


def _calculate_donchian(candles: list, period: int) -> tuple[list[float], list[float]]:
    """Calculate Donchian Channel (highest high / lowest low over period).

    Args:
        candles: List of Candle objects with high_price, low_price
        period: Lookback period

    Returns:
        Tuple of (upper, lower) lists — None for insufficient data
    """
    upper = []
    lower = []
    for i in range(len(candles)):
        if i < period - 1:
            upper.append(None)
            lower.append(None)
        else:
            highs = [candles[j].high_price for j in range(i - period + 1, i + 1)]
            lows = [candles[j].low_price for j in range(i - period + 1, i + 1)]
            upper.append(max(highs))
            lower.append(min(lows))
    return upper, lower


def donchian_breakout(entry_period: int = 20, exit_period: int = 10) -> Callable:
    """Donchian Channel Breakout Strategy (Turtle Trading).

    Simplified version of Richard Dennis's Turtle Trading rules. Buys on
    breakout above the entry-period high channel and sells on breakdown
    below the exit-period low channel.

    Args:
        entry_period: Lookback for entry channel (highest high)
        exit_period: Lookback for exit channel (lowest low)

    Returns:
        Strategy function compatible with Backtester.run()
    """
    min_bars = max(entry_period, exit_period) + 1

    def strategy_fn(candles: list[Candle], position: dict | None) -> str | None:
        if len(candles) < min_bars:
            return None

        entry_upper, _ = _calculate_donchian(candles, entry_period)
        _, exit_lower = _calculate_donchian(candles, exit_period)

        if entry_upper[-1] is None or exit_lower[-1] is None:
            return None

        # Compare current close to *previous* bar's channel value to detect breakout
        if entry_upper[-2] is None or exit_lower[-2] is None:
            return None

        current_close = candles[-1].close_price

        # Buy: close breaks above entry-period high channel
        if current_close > entry_upper[-2] and position is None:
            return 'buy'

        # Sell: close breaks below exit-period low channel
        if (current_close < exit_lower[-2]
                and position and position['side'] == 'long'):
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


def rsi2_connors(
    rsi_period: int = 2,
    sma_period: int = 200,
    oversold: float = 10,
    overbought: float = 90,
) -> Callable:
    """RSI(2) Connors Strategy.

    Larry Connors' short-term mean reversion with a long-term trend filter.
    Uses an ultra-short RSI(2) to catch extreme oversold/overbought readings
    while the 200-day SMA ensures we only trade in the direction of the trend.

    Args:
        rsi_period: RSI period (default 2)
        sma_period: Trend filter SMA period (default 200)
        oversold: RSI level considered oversold — buy signal (default 10)
        overbought: RSI level considered overbought — sell signal (default 90)

    Returns:
        Strategy function compatible with Backtester.run()
    """
    min_bars = max(rsi_period + 1, sma_period)

    def strategy_fn(candles: list[Candle], position: dict | None) -> str | None:
        if len(candles) < min_bars:
            return None

        prices = [c.close_price for c in candles]
        rsi_values = _calculate_rsi(prices, rsi_period)
        sma_values = _calculate_sma(prices, sma_period)

        if rsi_values[-1] is None or sma_values[-1] is None:
            return None

        current_price = prices[-1]
        current_rsi = rsi_values[-1]
        current_sma = sma_values[-1]

        # Buy: price above 200 SMA (uptrend) AND RSI(2) < oversold
        if current_price > current_sma and current_rsi < oversold and position is None:
            return 'buy'

        # Sell: RSI(2) > overbought
        if current_rsi > overbought and position and position['side'] == 'long':
            return 'sell'

        return None

    return strategy_fn


def macd_crossover(fast: int = 12, slow: int = 26, signal: int = 9) -> Callable:
    """MACD Crossover Strategy.

    Classic trend-following strategy using the Moving Average Convergence
    Divergence indicator. Buys when the MACD line crosses above the signal
    line and sells on the opposite crossover.

    Args:
        fast: Fast EMA period (default 12)
        slow: Slow EMA period (default 26)
        signal: Signal line EMA period (default 9)

    Returns:
        Strategy function compatible with Backtester.run()
    """
    min_bars = slow + signal + 1

    def strategy_fn(candles: list[Candle], position: dict | None) -> str | None:
        if len(candles) < min_bars:
            return None

        prices = [c.close_price for c in candles]
        fast_ema = _calculate_ema(prices, fast)
        slow_ema = _calculate_ema(prices, slow)

        # MACD line = fast EMA - slow EMA
        macd_line = []
        for i in range(len(prices)):
            if fast_ema[i] is None or slow_ema[i] is None:
                macd_line.append(None)
            else:
                macd_line.append(fast_ema[i] - slow_ema[i])

        # Signal line = EMA of MACD (replace None with 0 for EMA calc start)
        macd_for_ema = [v if v is not None else 0.0 for v in macd_line]
        signal_line = _calculate_ema(macd_for_ema, signal)

        if (macd_line[-1] is None or macd_line[-2] is None
                or signal_line[-1] is None or signal_line[-2] is None):
            return None

        macd_now, macd_prev = macd_line[-1], macd_line[-2]
        sig_now, sig_prev = signal_line[-1], signal_line[-2]

        # Buy: MACD crosses above signal
        if macd_prev <= sig_prev and macd_now > sig_now and position is None:
            return 'buy'

        # Sell: MACD crosses below signal
        if (macd_prev >= sig_prev and macd_now < sig_now
                and position and position['side'] == 'long'):
            return 'sell'

        return None

    return strategy_fn


def golden_cross(fast_period: int = 50, slow_period: int = 200) -> Callable:
    """Golden Cross / Death Cross Strategy (50/200 SMA).

    Classic long-term trend-following strategy. Buys on the golden cross
    (50 SMA crosses above 200 SMA) and sells on the death cross (50 SMA
    crosses below 200 SMA).

    Args:
        fast_period: Fast SMA period (default 50)
        slow_period: Slow SMA period (default 200)

    Returns:
        Strategy function compatible with Backtester.run()
    """
    min_bars = slow_period + 1

    def strategy_fn(candles: list[Candle], position: dict | None) -> str | None:
        if len(candles) < min_bars:
            return None

        prices = [c.close_price for c in candles]
        fast_sma = _calculate_sma(prices, fast_period)
        slow_sma = _calculate_sma(prices, slow_period)

        if (fast_sma[-1] is None or fast_sma[-2] is None
                or slow_sma[-1] is None or slow_sma[-2] is None):
            return None

        fast_now, fast_prev = fast_sma[-1], fast_sma[-2]
        slow_now, slow_prev = slow_sma[-1], slow_sma[-2]

        # Buy: golden cross (fast crosses above slow)
        if fast_prev <= slow_prev and fast_now > slow_now and position is None:
            return 'buy'

        # Sell: death cross (fast crosses below slow)
        if (fast_prev >= slow_prev and fast_now < slow_now
                and position and position['side'] == 'long'):
            return 'sell'

        return None

    return strategy_fn


def keltner_squeeze(
    keltner_period: int = 20,
    keltner_atr_mult: float = 1.5,
    bb_period: int = 20,
    bb_std: float = 2.0,
) -> Callable:
    """Keltner Channel Squeeze Strategy.

    Detects volatility squeezes where Bollinger Bands contract inside Keltner
    Channels, then trades the breakout direction when the squeeze releases.
    Inspired by John Carter's TTM Squeeze indicator.

    Args:
        keltner_period: EMA/ATR period for Keltner Channel (default 20)
        keltner_atr_mult: ATR multiplier for Keltner bands (default 1.5)
        bb_period: Bollinger Bands period (default 20)
        bb_std: Bollinger Bands standard deviation multiplier (default 2.0)

    Returns:
        Strategy function compatible with Backtester.run()
    """
    min_bars = max(keltner_period, bb_period) + 2  # +2 for squeeze state tracking

    was_squeezing = False

    def strategy_fn(candles: list[Candle], position: dict | None) -> str | None:
        nonlocal was_squeezing

        if len(candles) < min_bars:
            return None

        prices = [c.close_price for c in candles]

        # Keltner Channel: middle = EMA, bands = middle ± mult * ATR
        keltner_mid = _calculate_ema(prices, keltner_period)
        atr_values = _calculate_atr(candles, keltner_period)

        if keltner_mid[-1] is None or atr_values[-1] is None:
            return None

        kc_upper = keltner_mid[-1] + keltner_atr_mult * atr_values[-1]
        kc_lower = keltner_mid[-1] - keltner_atr_mult * atr_values[-1]

        # Bollinger Bands
        bb_upper, bb_mid, bb_lower = _calculate_bollinger_bands(prices, bb_period, bb_std)

        if bb_upper[-1] is None or bb_lower[-1] is None:
            return None

        # Squeeze detection: BB inside KC
        is_squeezing = bb_lower[-1] > kc_lower and bb_upper[-1] < kc_upper

        current_price = prices[-1]

        # Squeeze release: was squeezing, now not
        if was_squeezing and not is_squeezing:
            was_squeezing = is_squeezing
            # Buy on upward breakout
            if current_price > keltner_mid[-1] and position is None:
                return 'buy'
        else:
            was_squeezing = is_squeezing

        # Sell: price falls below Keltner middle
        if (current_price < keltner_mid[-1]
                and position and position['side'] == 'long'):
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


def _calculate_net_distribution(
    candles: list, period: int = 20, top_pct: float = 0.25
) -> float:
    """Calculate Net Distribution — volume direction indicator.

    Looks at the highest-volume bars over a lookback period and measures
    whether those high-volume bars were predominantly up days or down days.

    Args:
        candles: List of Candle objects (needs close_price, open_price, volume)
        period: Lookback period (default 20)
        top_pct: Fraction of bars to consider as "high volume" (default 0.25)

    Returns:
        Ratio of up-days among high-volume bars (0.0 to 1.0).
        Values > 0.5 indicate bullish volume direction.
        Returns 0.5 if insufficient data or no high-volume bars.
    """
    if len(candles) < period:
        return 0.5

    recent = candles[-period:]

    # Sort by volume descending, take top_pct
    sorted_by_vol = sorted(recent, key=lambda c: c.volume, reverse=True)
    n_top = max(1, int(period * top_pct))
    high_vol_bars = sorted_by_vol[:n_top]

    up_days = sum(1 for c in high_vol_bars if c.close_price > c.open_price)
    total = len(high_vol_bars)

    if total == 0:
        return 0.5

    return up_days / total


def volume_confirmed_breakout(
    volume_period: int = 20,
    top_pct: float = 0.25,
    threshold: float = 0.6,
    sma_period: int = 50,
) -> Callable:
    """Volume Confirmed Breakout Strategy.

    Combines SMA trend direction with a volume direction filter
    (Net Distribution). The key insight from analysing 370K chart patterns:
    volume *direction* matters more than volume magnitude.

    Buy when close crosses above the SMA AND high-volume bars are
    predominantly up days. Sell when close crosses below SMA OR high-volume
    bars turn bearish.

    Args:
        volume_period: Lookback for Net Distribution (default 20)
        top_pct: Fraction of bars treated as high-volume (default 0.25)
        threshold: Net Distribution threshold for bullish confirmation
            (default 0.6 — 60 %+ of high-volume days were up)
        sma_period: SMA period for trend filter (default 50)

    Returns:
        Strategy function compatible with Backtester.run()
    """
    min_bars = max(sma_period, volume_period) + 1

    def strategy_fn(candles: list[Candle], position: dict | None) -> str | None:
        if len(candles) < min_bars:
            return None

        prices = [c.close_price for c in candles]
        sma = _calculate_sma(prices, sma_period)

        if sma[-1] is None or sma[-2] is None:
            return None

        nd = _calculate_net_distribution(candles, volume_period, top_pct)
        current_price = prices[-1]
        prev_price = prices[-2]

        # Buy: close crosses above SMA AND net distribution is bullish
        if (prev_price <= sma[-2] and current_price > sma[-1]
                and nd > threshold and position is None):
            return 'buy'

        # Sell: close crosses below SMA OR volume turns bearish
        if position and position['side'] == 'long':
            if current_price < sma[-1] or nd < (1 - threshold):
                return 'sell'

        return None

    return strategy_fn


def _detect_bull_flag(
    candles: list,
    pole_min_pct: float = 5.0,
    flag_max_bars: int = 15,
    flag_retrace_max: float = 0.5,
) -> dict | None:
    """Detect a bull flag pattern at the current bar.

    A bull flag has two parts:
      1. Pole: a sharp upward move (>= pole_min_pct) over a short period
      2. Flag: consolidation / slight pullback that retraces <= flag_retrace_max
         of the pole, lasting <= flag_max_bars

    Args:
        candles: List of Candle objects (at least 30 bars recommended)
        pole_min_pct: Minimum gain for the pole in percent (default 5.0)
        flag_max_bars: Maximum bars the flag may last (default 15)
        flag_retrace_max: Maximum fraction of the pole the flag may retrace
            (default 0.5)

    Returns:
        Dict with 'flag_high' and 'flag_low' if pattern detected, else None.
    """
    lookback = 30
    if len(candles) < lookback:
        return None

    window = candles[-lookback:]

    # Try to find a pole ending at various points, followed by a flag up to now
    for pole_end in range(5, lookback - 3):
        # Pole: search backwards from pole_end for the pole start
        for pole_start in range(0, pole_end - 1):
            pole_low = window[pole_start].low_price
            pole_high = window[pole_end].high_price
            pole_gain_pct = ((pole_high - pole_low) / pole_low) * 100

            if pole_gain_pct < pole_min_pct:
                continue

            # Flag: bars from pole_end+1 to end of window
            flag_bars = window[pole_end + 1:]
            if not flag_bars or len(flag_bars) > flag_max_bars:
                continue

            flag_high = max(c.high_price for c in flag_bars)
            flag_low = min(c.low_price for c in flag_bars)

            # Flag should not retrace more than flag_retrace_max of pole
            pole_height = pole_high - pole_low
            retrace = pole_high - flag_low
            if pole_height > 0 and retrace / pole_height > flag_retrace_max:
                continue

            # Flag high should not extend significantly above pole high
            if flag_high > pole_high * 1.02:
                continue

            return {'flag_high': flag_high, 'flag_low': flag_low}

    return None


def bull_flag_breakout(
    pole_min_pct: float = 5.0,
    flag_max_bars: int = 15,
    flag_retrace_max: float = 0.5,
    volume_confirm: bool = True,
) -> Callable:
    """Bull Flag Breakout Strategy.

    Detects bull flag continuation patterns and trades the breakout.
    The bull flag is the highest-performing continuation pattern found
    in the 370K chart pattern study.

    Buy when a bull flag is detected and close breaks above the flag's
    upper boundary. Uses time-based exit (20 bars), stop loss (flag low),
    and profit target (10%).

    Args:
        pole_min_pct: Minimum pole gain percentage (default 5.0)
        flag_max_bars: Maximum flag duration in bars (default 15)
        flag_retrace_max: Maximum flag retracement as fraction of pole
            (default 0.5)
        volume_confirm: Require net_distribution > 0.5 during flag
            (default True)

    Returns:
        Strategy function compatible with Backtester.run()
    """
    # Mutable state for tracking entry
    state = {
        'entry_price': None,
        'entry_bar': 0,
        'flag_low': None,
        'bars_since_entry': 0,
    }

    def strategy_fn(candles: list[Candle], position: dict | None) -> str | None:
        if len(candles) < 31:
            return None

        current_price = candles[-1].close_price

        # If in a position, check exit conditions
        if position and position['side'] == 'long':
            state['bars_since_entry'] += 1

            # Stop loss: close drops below flag low
            if state['flag_low'] is not None and current_price < state['flag_low']:
                state['entry_price'] = None
                state['flag_low'] = None
                return 'sell'

            # Time exit: 20 bars after entry
            if state['bars_since_entry'] >= 20:
                state['entry_price'] = None
                state['flag_low'] = None
                return 'sell'

            # Profit target: 10% above entry
            if (state['entry_price'] is not None
                    and current_price > state['entry_price'] * 1.1):
                state['entry_price'] = None
                state['flag_low'] = None
                return 'sell'

            return None

        # Not in position — look for bull flag
        if position is not None:
            return None

        # Detect pattern on bars BEFORE current bar; current bar is the breakout candle
        flag = _detect_bull_flag(candles[:-1], pole_min_pct, flag_max_bars, flag_retrace_max)
        if flag is None:
            return None

        # Volume confirmation
        if volume_confirm:
            nd = _calculate_net_distribution(candles[:-1], period=20)
            if nd <= 0.5:
                return None

        # Breakout: current close above flag high
        if current_price > flag['flag_high']:
            state['entry_price'] = current_price
            state['flag_low'] = flag['flag_low']
            state['bars_since_entry'] = 0
            return 'buy'

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
