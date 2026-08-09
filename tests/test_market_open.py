"""Tests for is_market_open().

Payloads captured live 2026-08-09 (a Sunday) and for 2026-08-10 (a Monday).
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import responses

from pyhood import urls
from pyhood.client import PyhoodClient
from pyhood.http import Session

CLOSED = {"date": "2026-08-09", "is_open": False, "opens_at": None,
          "closes_at": None, "extended_opens_at": None, "extended_closes_at": None}

OPEN = {"date": "2026-08-10", "is_open": True,
        "opens_at": "2026-08-10T13:30:00Z", "closes_at": "2026-08-10T20:00:00Z",
        "extended_opens_at": "2026-08-10T13:00:00Z",
        "extended_closes_at": "2026-08-10T22:00:00Z"}


@pytest.fixture
def client():
    session = Session(timeout=5)
    session.set_auth("Bearer", "test-token")
    return PyhoodClient(session=session)


def _mock_hours(date, payload):
    responses.add(
        responses.GET, urls.MARKET_HOURS.format(market="XNAS", date=date),
        json=payload, status=200,
    )


def _at(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


class TestIsMarketOpen:
    @responses.activate
    def test_closed_on_a_weekend(self, client):
        _mock_hours("2026-08-09", CLOSED)
        with patch("pyhood.client.datetime") as dt:
            dt.now.return_value = _at("2026-08-09T17:00:00Z")
            dt.fromisoformat = datetime.fromisoformat
            assert client.is_market_open() is False

    @responses.activate
    def test_open_during_regular_session(self, client):
        _mock_hours("2026-08-10", OPEN)
        with patch("pyhood.client.datetime") as dt:
            dt.now.return_value = _at("2026-08-10T15:00:00Z")  # 11am ET
            dt.fromisoformat = datetime.fromisoformat
            assert client.is_market_open() is True

    @responses.activate
    def test_closed_before_the_bell(self, client):
        _mock_hours("2026-08-10", OPEN)
        with patch("pyhood.client.datetime") as dt:
            dt.now.return_value = _at("2026-08-10T13:00:00Z")  # 9am ET
            dt.fromisoformat = datetime.fromisoformat
            assert client.is_market_open() is False

    @responses.activate
    def test_extended_session_covers_premarket(self, client):
        _mock_hours("2026-08-10", OPEN)
        with patch("pyhood.client.datetime") as dt:
            dt.now.return_value = _at("2026-08-10T13:15:00Z")  # 9:15am ET
            dt.fromisoformat = datetime.fromisoformat
            assert client.is_market_open(extended_hours=True) is True

    @responses.activate
    def test_uses_new_york_date_not_utc(self, client):
        """At 01:00 UTC Tuesday it is still Monday evening in New York.

        A naive implementation would request Tuesday's hours and get the
        wrong answer for the evening session.
        """
        _mock_hours("2026-08-10", OPEN)  # Monday — the New York date
        with patch("pyhood.client.datetime") as dt:
            dt.now.return_value = _at("2026-08-11T01:00:00Z")  # 9pm ET Monday
            dt.fromisoformat = datetime.fromisoformat
            client.is_market_open(extended_hours=True)
        assert "2026-08-10" in responses.calls[0].request.url

    @responses.activate
    def test_missing_times_is_closed(self, client):
        _mock_hours("2026-08-10", {**OPEN, "opens_at": None, "closes_at": None})
        with patch("pyhood.client.datetime") as dt:
            dt.now.return_value = _at("2026-08-10T15:00:00Z")
            dt.fromisoformat = datetime.fromisoformat
            assert client.is_market_open() is False
