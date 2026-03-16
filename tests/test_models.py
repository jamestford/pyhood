"""Basic model tests."""

from pyhood.models import OptionContract, Quote


def test_quote_creation():
    q = Quote(symbol="AAPL", price=195.50, prev_close=193.00, change_pct=1.30)
    assert q.symbol == "AAPL"
    assert q.price == 195.50
    assert q.change_pct == 1.30


def test_option_vol_oi_ratio():
    opt = OptionContract(
        symbol="AAPL",
        option_type="call",
        strike=200.0,
        expiration="2026-04-17",
        mark=3.50,
        volume=5000,
        open_interest=2000,
    )
    assert opt.vol_oi_ratio == 2.5
    assert opt.cost_per_contract == 350.0


def test_option_vol_oi_ratio_zero_oi():
    opt = OptionContract(
        symbol="AAPL",
        option_type="put",
        strike=180.0,
        expiration="2026-04-17",
        mark=1.20,
        volume=100,
        open_interest=0,
    )
    assert opt.vol_oi_ratio == 0.0
