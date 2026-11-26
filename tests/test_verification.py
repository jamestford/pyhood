"""Tests for what pyhood does when Robinhood checks a new login.

The bank verification page below has the fields Robinhood sent to a real
account on 2026-11-25, read with scripts/login_trace.py. The values are
placeholders. The approval request ("prompt") responses hold only the fields
the code reads: no real one has been captured yet.
"""

import pytest
import responses

from pyhood import urls
from pyhood.auth import (
    BANK_VERIFICATION,
    UNKNOWN_STEP_POLLS,
    login,
    verification_name,
)
from pyhood.exceptions import (
    AuthError,
    DeviceApprovalRequiredError,
    OtherVerificationRequiredError,
)

MACHINE = "https://api.robinhood.com/pathfinder/user_machine/"
VIEW = "https://api.robinhood.com/pathfinder/inquiries/MACHINE-ID/user_view/"
PROMPT = "https://api.robinhood.com/push/CHALLENGE-ID/get_prompts_status/"

WORKFLOW = {
    "verification_workflow": {
        "id": "WORKFLOW-ID",
        "workflow_status": "workflow_status_internal_pending",
    },
}

TOKENS = {
    "access_token": "ACCESS",
    "token_type": "Bearer",
    "refresh_token": "REFRESH",
}


def text(words):
    return {"markdown": words, "text": words, "attributes": []}


def page(state):
    """A step with no approval request in it, as Robinhood sends it."""
    context = {
        "heading": text("HEADING"),
        "bank_list": [
            {
                "bank_account_type": "TYPE",
                "bank_account_nickname": "NICKNAME",
                "bank_account_number_last_four": "0000",
            },
        ],
        "subheading": text("SUBHEADING"),
        "fallback_heading": text("FALLBACK"),
        "fallback_cta_text": "FALLBACK",
        "fallback_subheading": text("FALLBACK"),
    }
    return {
        "page": "PAGE",
        "context": context,
        "type": "page",
        "type_context": {"page": "PAGE", "context": context},
        "sequence": 0,
        "state_name": state,
        "prev_state_name": "PREVIOUS",
        "polling_interval": None,
        "renderable_platforms": {"android": "0", "iOS": "0", "web": "0"},
        "http_status": 200,
        "should_replace_current_page": False,
        "toast": None,
        "locality": "US",
    }


def prompt(status="issued"):
    return {
        "context": {
            "sheriff_challenge": {"id": "CHALLENGE-ID", "type": "prompt", "status": status},
        },
        "state_name": "PROMPT",
    }


@pytest.fixture
def robinhood(tmp_path, monkeypatch):
    """A Robinhood that asks to check the login, with no waiting in the tests."""
    monkeypatch.setattr("pyhood.auth.DEFAULT_TOKEN_DIR", tmp_path)
    monkeypatch.setattr("pyhood.auth.time.sleep", lambda seconds: None)
    monkeypatch.setattr("pyhood.http.RATE_LIMIT_DELAY", 0)
    with responses.RequestsMock() as mock:
        mock.add(responses.POST, urls.LOGIN, json=WORKFLOW, status=403)
        mock.add(responses.POST, MACHINE, json={"id": "MACHINE-ID"})
        yield mock


def views(mock):
    return [call for call in mock.calls if call.request.url == VIEW]


class TestBankVerification:
    def test_it_stops_at_once(self, robinhood, tmp_path):
        robinhood.add(responses.GET, VIEW, json=page(BANK_VERIFICATION))

        with pytest.raises(OtherVerificationRequiredError) as raised:
            login("me@example.com", "PASSWORD", timeout=60)

        assert raised.value.state == "PlaidBankList"
        assert "a bank verification" in str(raised.value)
        assert "did not send an approval request" in str(raised.value)
        assert len(views(robinhood)) == 1
        assert not (tmp_path / "session.json").exists()

    def test_nobody_is_sent_to_their_phone(self, robinhood):
        robinhood.add(responses.GET, VIEW, json=page(BANK_VERIFICATION))
        told = []

        with pytest.raises(OtherVerificationRequiredError):
            login("me@example.com", "PASSWORD", timeout=60, on_verification=told.append)

        assert told == []

    def test_it_is_an_auth_error(self):
        """Code that already catches AuthError still catches this."""
        assert issubclass(OtherVerificationRequiredError, AuthError)


class TestAStepPyhoodDoesNotKnow:
    def test_it_gives_up_after_a_few_looks(self, robinhood):
        robinhood.add(responses.GET, VIEW, json=page("SomethingNew"))

        with pytest.raises(OtherVerificationRequiredError) as raised:
            login("me@example.com", "PASSWORD", timeout=60)

        assert raised.value.state == "SomethingNew"
        assert "a different check (SomethingNew)" in str(raised.value)
        assert len(views(robinhood)) == UNKNOWN_STEP_POLLS

    def test_a_step_that_turns_into_an_approval_request_is_followed(self, robinhood):
        """One unknown step on the way to the request is not a reason to stop."""
        robinhood.add(responses.GET, VIEW, json=page("Loading"))
        robinhood.add(responses.GET, VIEW, json=prompt())
        robinhood.add(responses.GET, PROMPT, json={"challenge_status": "validated"})
        robinhood.add(
            responses.POST, VIEW,
            json={"type_context": {"result": "workflow_status_approved"}},
        )
        robinhood.add(responses.POST, urls.LOGIN, json=TOKENS)

        login("me@example.com", "PASSWORD", timeout=60)

    def test_an_answer_with_no_step_name_is_asked_for_again(self, robinhood):
        robinhood.add(responses.GET, VIEW, json={})
        robinhood.add(responses.GET, VIEW, json={"context": None})
        robinhood.add(responses.GET, VIEW, json=page(BANK_VERIFICATION))

        with pytest.raises(OtherVerificationRequiredError):
            login("me@example.com", "PASSWORD", timeout=60)

        assert len(views(robinhood)) == 3


class TestApprovalRequest:
    def test_the_user_is_told_once_the_request_is_sent(self, robinhood, tmp_path):
        told = []
        robinhood.add(responses.GET, VIEW, json=prompt())
        robinhood.add(responses.GET, PROMPT, json={"challenge_status": "issued"})
        robinhood.add(responses.GET, PROMPT, json={"challenge_status": "validated"})
        robinhood.add(
            responses.POST, VIEW,
            json={"type_context": {"result": "workflow_status_approved"}},
        )
        robinhood.add(responses.POST, urls.LOGIN, json=TOKENS)

        login("me@example.com", "PASSWORD", timeout=60, on_verification=told.append)

        assert told == ["prompt"]
        assert (tmp_path / "session.json").exists()

    def test_no_approval_in_time(self, robinhood, monkeypatch):
        robinhood.add(responses.GET, VIEW, json=prompt())
        ticks = iter(range(0, 10_000, 4))
        monkeypatch.setattr("pyhood.auth.time.monotonic", lambda: next(ticks))
        robinhood.add(responses.GET, PROMPT, json={"challenge_status": "issued"})

        with pytest.raises(DeviceApprovalRequiredError):
            login("me@example.com", "PASSWORD", timeout=30)


class TestTheWaits:
    def test_the_first_look_comes_quickly(self, robinhood, monkeypatch):
        waits = []
        monkeypatch.setattr("pyhood.auth.time.sleep", waits.append)
        robinhood.add(responses.GET, VIEW, json=page("SomethingNew"))

        with pytest.raises(OtherVerificationRequiredError):
            login("me@example.com", "PASSWORD", timeout=60)

        assert waits == [2, 5, 5]


@pytest.mark.parametrize(
    ("state", "name"),
    [
        ("PlaidBankList", "a bank verification"),
        ("SomethingNew", "a different check (SomethingNew)"),
        (None, "a different check"),
        ("", "a different check"),
    ],
)
def test_verification_name(state, name):
    assert verification_name(state) == name


class TestNoTimeLimit:
    def test_zero_still_waits_for_the_approval(self, robinhood):
        """timeout=0 means no limit, not no waiting."""
        told = []
        robinhood.add(responses.GET, VIEW, json=prompt())
        robinhood.add(responses.GET, PROMPT, json={"challenge_status": "validated"})
        robinhood.add(
            responses.POST, VIEW,
            json={"type_context": {"result": "workflow_status_approved"}},
        )
        robinhood.add(responses.POST, urls.LOGIN, json=TOKENS)

        login("me@example.com", "PASSWORD", timeout=0, on_verification=told.append)

        assert told == ["prompt"]
