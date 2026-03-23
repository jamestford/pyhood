"""
Pyhood Backtesting Dashboard v1
Streamlit + Plotly dark-themed backtesting UI.
"""
import sys
import os
import sqlite3
import json
from pathlib import Path

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ── Path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "tv_scraper"))
sys.path.insert(0, str(ROOT))

from backtest.engine import BacktestConfig, run_backtest
from backtest.data import fetch_equity, fetch_alpaca
from backtest.strategies.ibs_spy import generate_signals as ibs_signals
from backtest.strategies.rsi_70_momentum import generate_signals as rsi70_signals
from backtest.strategies.donchian_breakout import generate_signals as donchian_signals

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Pyhood Backtest", page_icon="📈", layout="wide")

# ── Inline strategies ───────────────────────────────────────────────────────

def ema_crossover_signals(df: pd.DataFrame, params=None) -> pd.DataFrame:
    p = params or {}
    fast = p.get("fast", 9)
    slow = p.get("slow", 21)
    df = df.copy()
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    signal = np.where(ema_fast > ema_slow, 1, 0)
    df["signal"] = pd.Series(signal, index=df.index).shift(1).fillna(0).astype(int)
    return df


def macd_crossover_signals(df: pd.DataFrame, params=None) -> pd.DataFrame:
    p = params or {}
    fast = p.get("fast", 12)
    slow = p.get("slow", 26)
    signal_period = p.get("signal_period", 9)
    df = df.copy()
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    signal = np.where(macd_line > signal_line, 1, 0)
    df["signal"] = pd.Series(signal, index=df.index).shift(1).fillna(0).astype(int)
    return df


STRATEGIES = {
    "IBS": {"fn": ibs_signals, "params": {"low_ibs": 0.2, "high_ibs": 0.8, "max_bars": 30}},
    "RSI > 70 Momentum": {"fn": rsi70_signals, "params": {}},
    "Donchian Breakout": {"fn": donchian_signals, "params": {"length": 20}},
    "EMA Crossover": {"fn": ema_crossover_signals, "params": {"fast": 9, "slow": 21}},
    "MACD Crossover": {"fn": macd_crossover_signals, "params": {"fast": 12, "slow": 26, "signal_period": 9}},
}


# ── Helper: fetch data ─────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner="Fetching data...")
def load_data(ticker: str, source: str, interval: str, years: int) -> pd.DataFrame:
    interval_map_yf = {"1d": "1d", "1h": "1h", "15m": "15m", "5m": "5m"}
    interval_map_alp = {"1d": "1d", "1h": "1h", "15m": "15min", "5m": "5min"}
    if source == "yfinance":
        return fetch_equity(ticker, interval=interval_map_yf[interval], years=years)
    else:
        return fetch_alpaca(ticker, interval=interval_map_alp[interval], years=years)


# ── Helper: run a strategy ──────────────────────────────────────────────────

def run_strategy(df, strategy_name, params, capital, position_pct):
    strat = STRATEGIES[strategy_name]
    sig_df = strat["fn"](df.copy(), params)
    config = BacktestConfig(
        initial_capital=capital,
        position_size_pct=position_pct,
        slippage_pct=0.01,
        commission_per_trade=1.0,
    )
    return run_backtest(sig_df, config)


# ── Helper: build charts ───────────────────────────────────────────────────

def build_price_chart(df, result):
    """Candlestick + trade markers + equity + drawdown."""
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.5, 0.3, 0.2],
        vertical_spacing=0.03,
        subplot_titles=("Price + Trades", "Equity Curve", "Drawdown"),
    )
    # Candlesticks
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"],
        name="Price", increasing_line_color="#00cc96", decreasing_line_color="#ef553b",
    ), row=1, col=1)

    # Trade markers
    if result.trades:
        buy_dates = [t.entry_date for t in result.trades]
        buy_prices = [t.entry_price for t in result.trades]
        sell_dates = [t.exit_date for t in result.trades]
        sell_prices = [t.exit_price for t in result.trades]
        colors = ["#00cc96" if t.pnl > 0 else "#ef553b" for t in result.trades]

        fig.add_trace(go.Scatter(
            x=buy_dates, y=buy_prices, mode="markers",
            marker=dict(symbol="triangle-up", size=10, color="#00cc96", opacity=0.7),
            name="Buy",
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=sell_dates, y=sell_prices, mode="markers",
            marker=dict(symbol="triangle-down", size=10, color=colors, opacity=0.7),
            name="Sell",
        ), row=1, col=1)

    # Equity curve
    fig.add_trace(go.Scatter(
        x=result.equity_curve.index, y=result.equity_curve.values,
        name="Equity", line=dict(color="#636efa", width=2),
    ), row=2, col=1)

    # Drawdown
    fig.add_trace(go.Scatter(
        x=result.drawdown_curve.index, y=result.drawdown_curve.values * 100,
        name="Drawdown %", fill="tozeroy",
        line=dict(color="#ef553b", width=1),
        fillcolor="rgba(239,85,59,0.3)",
    ), row=3, col=1)

    fig.update_layout(
        template="plotly_dark", height=900,
        xaxis_rangeslider_visible=False,
        showlegend=False,
        margin=dict(l=50, r=20, t=40, b=30),
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="$", row=2, col=1)
    fig.update_yaxes(title_text="%", row=3, col=1)
    return fig


def metrics_row(result):
    cols = st.columns(7)
    pnl_color = "green" if result.net_profit >= 0 else "red"
    metrics = [
        ("Total P&L", f"${result.net_profit:,.2f}", pnl_color),
        ("CAGR", f"{result.cagr:.2f}%", None),
        ("Max DD", f"{result.max_drawdown:.2f}%", "red"),
        ("Sharpe", f"{result.sharpe:.2f}", None),
        ("Profit Factor", f"{result.profit_factor:.2f}", None),
        ("Win Rate", f"{result.win_rate:.1f}%", None),
        ("Trades", f"{result.total_trades}", None),
    ]
    for col, (label, val, color) in zip(cols, metrics):
        if color:
            col.markdown(f"**{label}**<br><span style='color:{color};font-size:1.3em'>{val}</span>", unsafe_allow_html=True)
        else:
            col.metric(label, val)


def trade_table(result):
    if not result.trades:
        st.info("No trades generated.")
        return
    rows = []
    for t in result.trades:
        bars = 0
        try:
            bars = (t.exit_date - t.entry_date).days
        except Exception:
            pass
        rows.append({
            "Entry": t.entry_date.strftime("%Y-%m-%d") if hasattr(t.entry_date, "strftime") else str(t.entry_date),
            "Exit": t.exit_date.strftime("%Y-%m-%d") if hasattr(t.exit_date, "strftime") else str(t.exit_date),
            "Dir": "Long" if t.direction == 1 else "Short",
            "Entry $": f"{t.entry_price:.2f}",
            "Exit $": f"{t.exit_price:.2f}",
            "P&L $": f"{t.pnl:.2f}",
            "P&L %": f"{t.pnl_pct:.2f}%",
            "Bars": bars,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE 1: Strategy Backtester
# ═══════════════════════════════════════════════════════════════════════════

def page_backtester():
    st.header("📈 Strategy Backtester")

    # ── Sidebar inputs ──
    with st.sidebar:
        st.subheader("Settings")
        ticker = st.text_input("Ticker", value="SPY")
        source = st.selectbox("Data Source", ["yfinance", "Alpaca"])
        timeframe = st.selectbox("Timeframe", ["1d", "1h", "15m", "5m"])
        years = st.slider("Years of Data", 1, 35, 5)
        strategy_name = st.selectbox("Strategy", list(STRATEGIES.keys()))
        capital = st.number_input("Initial Capital ($)", value=100000, step=10000)
        position_pct = st.slider("Position Size (%)", 1, 100, 100)

        # Dynamic params
        st.subheader("Strategy Parameters")
        default_params = STRATEGIES[strategy_name]["params"].copy()
        params = {}
        if strategy_name == "IBS":
            params["low_ibs"] = st.slider("Low IBS Threshold", 0.05, 0.5, default_params["low_ibs"], 0.05)
            params["high_ibs"] = st.slider("High IBS Threshold", 0.5, 0.95, default_params["high_ibs"], 0.05)
            params["max_bars"] = st.slider("Max Bars Held", 5, 60, default_params["max_bars"])
        elif strategy_name == "RSI > 70 Momentum":
            pass  # no tunable params in current impl
        elif strategy_name == "Donchian Breakout":
            params["length"] = st.slider("Channel Length", 5, 50, default_params["length"])
        elif strategy_name == "EMA Crossover":
            params["fast"] = st.slider("Fast EMA", 3, 50, default_params["fast"])
            params["slow"] = st.slider("Slow EMA", 10, 200, default_params["slow"])
        elif strategy_name == "MACD Crossover":
            params["fast"] = st.slider("MACD Fast", 5, 30, default_params["fast"])
            params["slow"] = st.slider("MACD Slow", 15, 50, default_params["slow"])
            params["signal_period"] = st.slider("Signal Period", 3, 20, default_params["signal_period"])

        run_btn = st.button("🚀 Run Backtest", type="primary", use_container_width=True)

    # ── Main area ──
    if run_btn:
        try:
            df = load_data(ticker, source, timeframe, years)
            result = run_strategy(df, strategy_name, params, capital, position_pct)
            st.session_state["last_result"] = result
            st.session_state["last_df"] = df
        except Exception as e:
            st.error(f"Error: {e}")
            return

    if "last_result" in st.session_state:
        result = st.session_state["last_result"]
        df = st.session_state["last_df"]
        metrics_row(result)
        st.plotly_chart(build_price_chart(df, result), use_container_width=True)
        with st.expander("📋 Trade Log", expanded=False):
            trade_table(result)
    else:
        st.info("Configure settings in the sidebar and click **Run Backtest**.")


# ═══════════════════════════════════════════════════════════════════════════
# PAGE 2: Strategy Comparison
# ═══════════════════════════════════════════════════════════════════════════

def page_comparison():
    st.header("⚔️ Strategy Comparison")

    with st.sidebar:
        st.subheader("Comparison Settings")
        ticker = st.text_input("Ticker", value="SPY", key="cmp_ticker")
        source = st.selectbox("Data Source", ["yfinance", "Alpaca"], key="cmp_source")
        timeframe = st.selectbox("Timeframe", ["1d", "1h", "15m", "5m"], key="cmp_tf")
        years = st.slider("Years", 1, 35, 5, key="cmp_years")
        capital = st.number_input("Capital ($)", value=100000, step=10000, key="cmp_cap")
        selected = st.multiselect("Strategies (2-4)", list(STRATEGIES.keys()),
                                  default=["IBS", "EMA Crossover"])
        run_cmp = st.button("🚀 Compare", type="primary", use_container_width=True)

    if run_cmp:
        if len(selected) < 2:
            st.warning("Select at least 2 strategies.")
            return
        try:
            df = load_data(ticker, source, timeframe, years)
        except Exception as e:
            st.error(f"Data error: {e}")
            return

        results = {}
        for name in selected:
            try:
                results[name] = run_strategy(df, name, STRATEGIES[name]["params"], capital, 100)
            except Exception as e:
                st.warning(f"{name} failed: {e}")

        if not results:
            return

        # Overlay equity curves
        fig = go.Figure()
        colors = ["#636efa", "#00cc96", "#ef553b", "#ffa15a"]
        for i, (name, res) in enumerate(results.items()):
            fig.add_trace(go.Scatter(
                x=res.equity_curve.index, y=res.equity_curve.values,
                name=name, line=dict(color=colors[i % len(colors)], width=2),
            ))
        fig.update_layout(template="plotly_dark", height=500, title="Equity Curves",
                          yaxis_title="$", margin=dict(l=50, r=20, t=50, b=30))
        st.plotly_chart(fig, use_container_width=True)

        # Metrics table
        rows = []
        for name, res in results.items():
            rows.append({
                "Strategy": name,
                "Net P&L": f"${res.net_profit:,.2f}",
                "CAGR %": f"{res.cagr:.2f}",
                "Max DD %": f"{res.max_drawdown:.2f}",
                "Sharpe": f"{res.sharpe:.2f}",
                "PF": f"{res.profit_factor:.2f}",
                "Win Rate %": f"{res.win_rate:.1f}",
                "Trades": res.total_trades,
            })
        mt = pd.DataFrame(rows)
        st.dataframe(mt, use_container_width=True, hide_index=True)

        # Highlight best
        best_sharpe = max(results, key=lambda k: results[k].sharpe)
        best_pf = max(results, key=lambda k: results[k].profit_factor)
        best_cagr = max(results, key=lambda k: results[k].cagr)
        st.success(f"🏆 Best Sharpe: **{best_sharpe}** | Best PF: **{best_pf}** | Best CAGR: **{best_cagr}**")


# ═══════════════════════════════════════════════════════════════════════════
# PAGE 3: Autoresearch Results
# ═══════════════════════════════════════════════════════════════════════════

def _compute_score(row):
    """Composite ranking score for a kept strategy."""
    ts = row.get("test_sharpe", 0) or 0
    tpf = row.get("test_profit_factor", 0) or 0
    twr = row.get("test_win_rate", 0) or 0
    og = row.get("overfit_gap", 0) or 0
    return (ts * 0.35) + (tpf * 0.25) + (twr / 100 * 0.20) + ((100 - abs(og)) / 100 * 0.20)


def page_autoresearch():
    st.header("🔬 Strategy Leaderboard")

    db_path = ROOT / "autoresearch_results" / "autoresearch_memory.db"
    if not db_path.exists():
        st.error(f"DB not found: `{db_path}`")
        return

    conn = sqlite3.connect(str(db_path))
    try:
        df = pd.read_sql_query("SELECT * FROM experiments ORDER BY id", conn)
    finally:
        conn.close()

    if df.empty:
        st.info("No experiments found yet. Run autoresearch to populate results.")
        return

    # Only kept strategies
    kept = df[df["kept"] == 1].copy()
    if kept.empty:
        st.warning(f"No strategies passed filters yet ({len(df)} total experiments run).")
        return

    # Fill NaN numerics with 0 for score calc
    numeric_cols = ["test_sharpe", "test_profit_factor", "test_win_rate",
                    "overfit_gap", "test_return", "test_max_drawdown", "test_trades",
                    "train_sharpe", "train_profit_factor", "train_win_rate",
                    "train_return", "train_max_drawdown", "train_trades"]
    for c in numeric_cols:
        if c in kept.columns:
            kept[c] = pd.to_numeric(kept[c], errors="coerce").fillna(0)

    # Compute composite score
    kept["score"] = kept.apply(_compute_score, axis=1)

    # ── Sidebar filters ──
    with st.sidebar:
        st.subheader("Leaderboard Filters")
        tickers = ["All"] + sorted(kept["ticker"].unique().tolist())
        sel_ticker = st.selectbox("Ticker", tickers, key="ar_ticker")

        min_trades = st.slider("Min Test Trades", 0, 100, 10, key="ar_min_trades")

        sort_options = {
            "Score": "score",
            "Test Sharpe": "test_sharpe",
            "Test Return": "test_return",
            "Win Rate": "test_win_rate",
            "Overfit Gap": "overfit_gap",
        }
        sort_label = st.selectbox("Sort By", list(sort_options.keys()), key="ar_sort")
        sort_col = sort_options[sort_label]

    # Apply filters
    filtered = kept.copy()
    if sel_ticker != "All":
        filtered = filtered[filtered["ticker"] == sel_ticker]
    if "test_trades" in filtered.columns:
        filtered = filtered[filtered["test_trades"] >= min_trades]

    if filtered.empty:
        st.warning("No strategies match current filters. Try lowering min trades or changing ticker.")
        return

    # Sort
    ascending = True if sort_col == "overfit_gap" else False
    filtered = filtered.sort_values(sort_col, ascending=ascending).reset_index(drop=True)
    filtered.insert(0, "rank", range(1, len(filtered) + 1))

    # ── Top Strategy Callout ──
    top = filtered.iloc[0]
    st.success(
        f"🏆 **#{1} — {top['strategy_name']}** ({top['ticker']})  •  "
        f"Score: **{top['score']:.2f}**"
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Test Sharpe", f"{top['test_sharpe']:.2f}")
    c2.metric("Test Return", f"{top['test_return']:.1f}%")
    c3.metric("Win Rate", f"{top['test_win_rate']:.1f}%")
    c4.metric("Max Drawdown", f"{top['test_max_drawdown']:.1f}%")
    c5.metric("Overfit Gap", f"{top['overfit_gap']:.1f}%")

    # ── Summary Stats ──
    avg_sharpe = filtered["test_sharpe"].mean()
    best_row = filtered.loc[filtered["test_sharpe"].idxmax()]
    ticker_list = ", ".join(sorted(filtered["ticker"].unique().tolist()))
    st.caption(
        f"**{len(filtered)}** strategies passed  |  "
        f"Avg Test Sharpe: **{avg_sharpe:.2f}**  |  "
        f"Best Sharpe: **{best_row['strategy_name']}** ({best_row['test_sharpe']:.2f})  |  "
        f"Tickers: {ticker_list}"
    )

    # ── Leaderboard Table ──
    st.subheader("Leaderboard")
    board = filtered[["rank", "strategy_name", "ticker", "score",
                       "test_sharpe", "test_return", "test_win_rate",
                       "overfit_gap", "test_trades"]].copy()
    board.columns = ["Rank", "Strategy", "Ticker", "Score",
                     "Test Sharpe", "Test Return %", "Win Rate %",
                     "Overfit Gap %", "Test Trades"]

    # Round for display
    for col in ["Score", "Test Sharpe"]:
        board[col] = board[col].round(2)
    for col in ["Test Return %", "Win Rate %", "Overfit Gap %"]:
        board[col] = board[col].round(1)
    board["Test Trades"] = board["Test Trades"].astype(int)

    st.dataframe(board, use_container_width=True, hide_index=True)

    # ── Strategy Detail ──
    st.subheader("Strategy Detail")
    detail_options = [
        f"#{r['rank']} — {r['Strategy']} ({r['Ticker']})"
        for _, r in board.iterrows()
    ]
    if not detail_options:
        return

    sel_detail = st.selectbox("Select a strategy", detail_options, key="ar_detail")
    sel_rank = int(sel_detail.split("#")[1].split(" ")[0])
    row = filtered[filtered["rank"] == sel_rank].iloc[0]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Train Metrics**")
        st.metric("Sharpe", f"{row.get('train_sharpe', 0):.2f}")
        st.metric("Return", f"{row.get('train_return', 0):.1f}%")
        st.metric("Max Drawdown", f"{row.get('train_max_drawdown', 0):.1f}%")
        st.metric("Win Rate", f"{row.get('train_win_rate', 0):.1f}%")
        st.metric("Profit Factor", f"{row.get('train_profit_factor', 0):.2f}")
        st.metric("Trades", f"{int(row.get('train_trades', 0))}")
    with col2:
        st.markdown("**Test Metrics**")
        st.metric("Sharpe", f"{row.get('test_sharpe', 0):.2f}")
        st.metric("Return", f"{row.get('test_return', 0):.1f}%")
        st.metric("Max Drawdown", f"{row.get('test_max_drawdown', 0):.1f}%")
        st.metric("Win Rate", f"{row.get('test_win_rate', 0):.1f}%")
        st.metric("Profit Factor", f"{row.get('test_profit_factor', 0):.2f}")
        st.metric("Trades", f"{int(row.get('test_trades', 0))}")

    # Overfit gap indicator
    gap_val = abs(row.get("overfit_gap", 0))
    if gap_val < 25:
        gap_color, gap_label = "green", "Low"
    elif gap_val < 50:
        gap_color, gap_label = "orange", "Moderate"
    else:
        gap_color, gap_label = "red", "High"
    st.markdown(
        f"**Overfit Gap:** <span style='color:{gap_color};font-size:1.2em'>"
        f"{row.get('overfit_gap', 0):.1f}% ({gap_label})</span>",
        unsafe_allow_html=True,
    )

    # Parameters
    try:
        params_raw = row.get("params_json", "{}")
        if params_raw and str(params_raw) != "nan":
            params_data = json.loads(params_raw)
            if params_data:
                st.markdown("**Parameters**")
                st.json(params_data)
    except Exception:
        pass

    # Regime breakdown
    try:
        regime_raw = row.get("regime_breakdown_json", "{}")
        if regime_raw and str(regime_raw) != "nan":
            regime_data = json.loads(regime_raw)
            if regime_data:
                st.markdown("**Regime Breakdown**")
                regime_df = pd.DataFrame(regime_data).T
                st.dataframe(regime_df, use_container_width=True)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Navigation
# ═══════════════════════════════════════════════════════════════════════════

PAGES = {
    "📈 Strategy Backtester": page_backtester,
    "⚔️ Strategy Comparison": page_comparison,
    "🔬 Autoresearch Results": page_autoresearch,
}

with st.sidebar:
    st.title("Pyhood")
    page = st.radio("Navigation", list(PAGES.keys()), label_visibility="collapsed")

PAGES[page]()
