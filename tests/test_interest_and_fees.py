"""Tests for interest payments, subscription fees and unified transfers.

Payloads captured from the live API on 2026-08-09, with account identifiers
replaced by placeholders.
"""

import pytest
import responses

from pyhood import urls
from pyhood.client import PyhoodClient
from pyhood.http import Session
from pyhood.models import InterestPayment, SubscriptionFee, UnifiedTransfer


@pytest.fixture
def client():
    session = Session(timeout=5)
    session.set_auth("Bearer", "test-token")
    return PyhoodClient(session=session)


class TestInterestPayments:
    SWEEPS = {
        "next": None,
        "previous": None,
        "results": [{
            "amount": {
                "amount": "25.76",
                "currency_code": "USD",
                "currency_id": "1072fc76-1862-41ab-82c2-485837590762",
            },
            "direction": "credit",
            "id": "sweep-1",
            "account_number": "ACCOUNT_NUMBER",
            "pay_date": "2026-07-31T21:00:00Z",
            "pay_period_start": "2026-07-31T21:00:00Z",
            "pay_period_end": "2026-07-31T21:00:00Z",
            "payout_type": "eom_payment",
            "reason": "interest_payment",
        }],
    }

    @responses.activate
    def test_nested_amount_is_flattened(self, client):
        """amount arrives as a nested object, not a bare string."""
        responses.add(
            responses.GET, urls.INTEREST_PAYMENTS, json=self.SWEEPS, status=200,
        )

        payments = client.get_interest_payments()
        assert len(payments) == 1
        p = payments[0]
        assert isinstance(p, InterestPayment)
        assert p.amount == 25.76
        assert p.currency == "USD"
        assert p.direction == "credit"
        assert p.payout_type == "eom_payment"
        assert p.reason == "interest_payment"

    @responses.activate
    def test_missing_amount_does_not_raise(self, client):
        responses.add(
            responses.GET, urls.INTEREST_PAYMENTS,
            json={"results": [{"id": "sweep-2"}]}, status=200,
        )

        assert client.get_interest_payments()[0].amount == 0.0

    @responses.activate
    def test_empty(self, client):
        responses.add(
            responses.GET, urls.INTEREST_PAYMENTS, json={"results": []}, status=200,
        )

        assert client.get_interest_payments() == []


class TestSubscriptionFees:
    @responses.activate
    def test_parses_fee(self, client):
        responses.add(
            responses.GET, urls.SUBSCRIPTION_FEES,
            json={"results": [{
                "id": "fee-1",
                "amount": "5.00",
                "credit": "0.00",
                "carry_forward_credit": "0.00",
                "date": "2026-08-04",
                "created_at": "2026-08-04T05:18:01.837129Z",
                "state": "posted",
                "account_number": "ACCOUNT_NUMBER",
            }]},
            status=200,
        )

        fees = client.get_subscription_fees()
        assert isinstance(fees[0], SubscriptionFee)
        assert fees[0].amount == 5.0
        assert fees[0].state == "posted"
        assert fees[0].date == "2026-08-04"


class TestUnifiedTransfers:
    @responses.activate
    def test_parses_internal_transfer(self, client):
        responses.add(
            responses.GET, urls.UNIFIED_TRANSFERS,
            json={"results": [{
                "id": "xfer-1",
                "originating_account_id": "ACCOUNT_A",
                "originating_account_type": "rhs_account",
                "receiving_account_id": "ACCOUNT_B",
                "receiving_account_type": "rhs_roth_ira",
                "transfer_type": "internal",
                "amount": "7000.00",
                "currency": "usd",
                "direction": "push",
                "state": "completed",
            }]},
            status=200,
        )

        t = client.get_unified_transfers()[0]
        assert isinstance(t, UnifiedTransfer)
        assert t.amount == 7000.0
        assert t.transfer_type == "internal"
        assert t.receiving_account_type == "rhs_roth_ira"


class TestMarginInterest:
    """Envelope verified live; no populated record observable."""

    @responses.activate
    def test_returns_raw_records(self, client):
        responses.add(
            responses.GET, urls.MARGIN_INTEREST,
            json={"results": [{"id": "mi-1", "anything": "preserved"}]}, status=200,
        )

        assert client.get_margin_interest() == [{"id": "mi-1", "anything": "preserved"}]

    @responses.activate
    def test_empty(self, client):
        responses.add(
            responses.GET, urls.MARGIN_INTEREST, json={"results": []}, status=200,
        )

        assert client.get_margin_interest() == []
