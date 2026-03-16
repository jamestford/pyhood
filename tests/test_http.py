"""Tests for HTTP session — rate limiting, retries, auth, pagination."""

import time

import responses

from pyhood.exceptions import APIError, RateLimitError
from pyhood.http import Session

import pytest


BASE = "https://api.robinhood.com"


class TestSession:
    def setup_method(self):
        self.session = Session(timeout=5)

    def test_initial_state(self):
        assert not self.session.is_authenticated
        assert "Authorization" not in self.session.headers

    def test_set_auth(self):
        self.session.set_auth("Bearer", "test-token-123")
        assert self.session.is_authenticated
        assert self.session.headers["Authorization"] == "Bearer test-token-123"

    def test_clear_auth(self):
        self.session.set_auth("Bearer", "test-token-123")
        self.session.clear_auth()
        assert not self.session.is_authenticated

    @responses.activate
    def test_get_success(self):
        responses.add(
            responses.GET,
            f"{BASE}/test/",
            json={"result": "ok"},
            status=200,
        )
        data = self.session.get(f"{BASE}/test/")
        assert data == {"result": "ok"}

    @responses.activate
    def test_post_success(self):
        responses.add(
            responses.POST,
            f"{BASE}/test/",
            json={"created": True},
            status=200,
        )
        data = self.session.post(f"{BASE}/test/", data={"key": "value"})
        assert data == {"created": True}

    @responses.activate
    def test_delete_success(self):
        responses.add(
            responses.DELETE,
            f"{BASE}/test/",
            json={},
            status=200,
        )
        data = self.session.delete(f"{BASE}/test/")
        assert data == {}

    @responses.activate
    def test_empty_response(self):
        responses.add(
            responses.GET,
            f"{BASE}/test/",
            body="",
            status=200,
        )
        data = self.session.get(f"{BASE}/test/")
        assert data == {}

    @responses.activate
    def test_auth_error_401(self):
        responses.add(
            responses.GET,
            f"{BASE}/test/",
            json={"detail": "Not authenticated"},
            status=401,
        )
        with pytest.raises(APIError) as exc_info:
            self.session.get(f"{BASE}/test/")
        assert exc_info.value.status_code == 401

    @responses.activate
    def test_auth_error_403(self):
        responses.add(
            responses.GET,
            f"{BASE}/test/",
            json={"detail": "Forbidden"},
            status=403,
        )
        with pytest.raises(APIError) as exc_info:
            self.session.get(f"{BASE}/test/")
        assert exc_info.value.status_code == 403

    @responses.activate
    def test_rate_limit_retry_then_success(self):
        responses.add(
            responses.GET,
            f"{BASE}/test/",
            json={},
            status=429,
            headers={"Retry-After": "0"},
        )
        responses.add(
            responses.GET,
            f"{BASE}/test/",
            json={"ok": True},
            status=200,
        )
        data = self.session.get(f"{BASE}/test/")
        assert data == {"ok": True}
        assert len(responses.calls) == 2

    @responses.activate
    def test_rate_limit_exhausted(self):
        for _ in range(3):
            responses.add(
                responses.GET,
                f"{BASE}/test/",
                json={},
                status=429,
                headers={"Retry-After": "0"},
            )
        with pytest.raises(RateLimitError):
            self.session.get(f"{BASE}/test/")

    @responses.activate
    def test_pagination(self):
        responses.add(
            responses.GET,
            f"{BASE}/list/",
            json={
                "results": [{"id": 1}, {"id": 2}],
                "next": f"{BASE}/list/?cursor=page2",
            },
            status=200,
        )
        responses.add(
            responses.GET,
            f"{BASE}/list/?cursor=page2",
            json={
                "results": [{"id": 3}],
                "next": None,
            },
            status=200,
        )
        results = self.session.get_paginated(f"{BASE}/list/")
        assert len(results) == 3
        assert results[0]["id"] == 1
        assert results[2]["id"] == 3

    @responses.activate
    def test_pagination_empty(self):
        responses.add(
            responses.GET,
            f"{BASE}/list/",
            json={"results": [], "next": None},
            status=200,
        )
        results = self.session.get_paginated(f"{BASE}/list/")
        assert results == []

    def test_rate_limit_enforced(self):
        """Verify minimum delay between requests."""
        self.session._last_request_at = time.monotonic()
        start = time.monotonic()
        self.session._rate_limit()
        elapsed = time.monotonic() - start
        # Should have waited at least some time (RATE_LIMIT_DELAY = 0.25)
        assert elapsed >= 0.2

    @responses.activate
    def test_server_error_retries(self):
        """Connection errors should retry."""
        responses.add(
            responses.GET,
            f"{BASE}/test/",
            body=ConnectionError("connection reset"),
        )
        responses.add(
            responses.GET,
            f"{BASE}/test/",
            body=ConnectionError("connection reset"),
        )
        responses.add(
            responses.GET,
            f"{BASE}/test/",
            body=ConnectionError("connection reset"),
        )
        with pytest.raises(APIError, match="failed after"):
            self.session.get(f"{BASE}/test/")
