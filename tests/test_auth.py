"""Tests for authentication — token store, login flow, error handling."""

import json
import time
from pathlib import Path

import pytest
import responses

from hood import urls
from hood.auth import TokenStore, generate_device_token, login, logout, get_session
from hood.exceptions import AuthError, LoginTimeoutError


class TestGenerateDeviceToken:
    def test_format(self):
        token = generate_device_token()
        # Should be hex with dashes: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (32 hex + 4 dashes)
        parts = token.split("-")
        assert len(parts) == 5
        # All parts should be valid hex
        for part in parts:
            int(part, 16)

    def test_unique(self):
        tokens = {generate_device_token() for _ in range(100)}
        assert len(tokens) == 100  # All unique


class TestTokenStore:
    def setup_method(self, tmp_path=None):
        self.tmp = Path("/tmp/hood-test-tokens")
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.path = self.tmp / "test-session.json"
        if self.path.exists():
            self.path.unlink()
        self.store = TokenStore(path=self.path)

    def teardown_method(self):
        if self.path.exists():
            self.path.unlink()

    def test_load_no_file(self):
        assert self.store.load() is None

    def test_save_and_load(self):
        self.store.save(
            access_token="acc-123",
            token_type="Bearer",
            refresh_token="ref-456",
            device_token="dev-789",
        )
        data = self.store.load()
        assert data is not None
        assert data["access_token"] == "acc-123"
        assert data["token_type"] == "Bearer"
        assert data["refresh_token"] == "ref-456"
        assert data["device_token"] == "dev-789"
        assert "saved_at" in data

    def test_clear(self):
        self.store.save(
            access_token="acc",
            token_type="Bearer",
            refresh_token="ref",
            device_token="dev",
        )
        assert self.path.exists()
        self.store.clear()
        assert not self.path.exists()
        assert self.store.load() is None

    def test_clear_no_file(self):
        """Clear when no file exists shouldn't error."""
        self.store.clear()

    def test_load_corrupt_file(self):
        with open(self.path, "w") as f:
            f.write("not json {{{")
        assert self.store.load() is None

    def test_load_missing_fields(self):
        with open(self.path, "w") as f:
            json.dump({"access_token": "only-one-field"}, f)
        assert self.store.load() is None

    def test_device_token_property(self):
        self.store.save(
            access_token="acc",
            token_type="Bearer",
            refresh_token="ref",
            device_token="my-device-token",
        )
        assert self.store.device_token == "my-device-token"

    def test_device_token_no_file(self):
        assert self.store.device_token is None


class TestLoginFlow:
    @responses.activate
    def test_login_success(self):
        """Fresh login with valid credentials."""
        # Login endpoint
        responses.add(
            responses.POST,
            urls.LOGIN,
            json={
                "access_token": "new-access-token",
                "token_type": "Bearer",
                "refresh_token": "new-refresh-token",
                "expires_in": 86400,
                "scope": "internal",
            },
            status=200,
        )

        token_path = Path("/tmp/hood-test-login-session.json")
        if token_path.exists():
            token_path.unlink()

        session = login(
            username="test@example.com",
            password="testpass",
            timeout=10,
            token_path=token_path,
        )

        assert session.is_authenticated
        assert "Bearer new-access-token" in session.headers.get("Authorization", "")

        # Token should be persisted
        assert token_path.exists()
        with open(token_path) as f:
            stored = json.load(f)
        assert stored["access_token"] == "new-access-token"

        # Cleanup
        token_path.unlink()

    @responses.activate
    def test_login_cached_session_valid(self):
        """Login with valid cached session skips fresh login."""
        token_path = Path("/tmp/hood-test-cached-session.json")
        with open(token_path, "w") as f:
            json.dump({
                "access_token": "cached-token",
                "token_type": "Bearer",
                "refresh_token": "cached-refresh",
                "device_token": "cached-device",
                "saved_at": time.time(),
            }, f)

        # Validation call succeeds
        responses.add(
            responses.GET,
            urls.POSITIONS,
            json={"results": []},
            status=200,
        )

        session = login(
            username="test@example.com",
            password="testpass",
            timeout=10,
            token_path=token_path,
        )

        assert session.is_authenticated
        # Should only have made the validation call, not the login call
        assert len(responses.calls) == 1
        assert urls.POSITIONS in responses.calls[0].request.url

        token_path.unlink()

    @responses.activate
    def test_login_cached_session_expired(self):
        """Expired cached session falls through to fresh login."""
        token_path = Path("/tmp/hood-test-expired-session.json")
        with open(token_path, "w") as f:
            json.dump({
                "access_token": "expired-token",
                "token_type": "Bearer",
                "refresh_token": "old-refresh",
                "device_token": "old-device",
                "saved_at": time.time() - 100000,
            }, f)

        # Validation fails (expired)
        responses.add(
            responses.GET,
            urls.POSITIONS,
            json={"detail": "Not authenticated"},
            status=401,
        )

        # Fresh login succeeds
        responses.add(
            responses.POST,
            urls.LOGIN,
            json={
                "access_token": "fresh-token",
                "token_type": "Bearer",
                "refresh_token": "fresh-refresh",
                "expires_in": 86400,
                "scope": "internal",
            },
            status=200,
        )

        session = login(
            username="test@example.com",
            password="testpass",
            timeout=10,
            token_path=token_path,
        )

        assert session.is_authenticated
        assert "Bearer fresh-token" in session.headers.get("Authorization", "")

        token_path.unlink()

    def test_login_no_credentials(self):
        """Login without credentials and no cached session should raise."""
        token_path = Path("/tmp/hood-test-no-creds.json")
        if token_path.exists():
            token_path.unlink()

        with pytest.raises(AuthError, match="Username and password required"):
            login(token_path=token_path, timeout=5)

    @responses.activate
    def test_login_empty_response(self):
        """Empty response from login endpoint should raise."""
        responses.add(
            responses.POST,
            urls.LOGIN,
            json={},
            status=200,
        )

        token_path = Path("/tmp/hood-test-empty-response.json")
        if token_path.exists():
            token_path.unlink()

        with pytest.raises(AuthError, match="Empty response"):
            login(
                username="test@example.com",
                password="testpass",
                timeout=5,
                token_path=token_path,
            )

    @responses.activate
    def test_login_no_access_token(self):
        """Response without access_token should raise."""
        responses.add(
            responses.POST,
            urls.LOGIN,
            json={"something": "else"},
            status=200,
        )

        token_path = Path("/tmp/hood-test-no-token.json")
        if token_path.exists():
            token_path.unlink()

        with pytest.raises(AuthError, match="unexpected response"):
            login(
                username="test@example.com",
                password="testpass",
                timeout=5,
                token_path=token_path,
            )

    @responses.activate
    def test_login_without_storing(self):
        """Login with store_session=False shouldn't write to disk."""
        responses.add(
            responses.POST,
            urls.LOGIN,
            json={
                "access_token": "ephemeral-token",
                "token_type": "Bearer",
                "refresh_token": "ephemeral-refresh",
                "expires_in": 86400,
                "scope": "internal",
            },
            status=200,
        )

        token_path = Path("/tmp/hood-test-no-store.json")
        if token_path.exists():
            token_path.unlink()

        session = login(
            username="test@example.com",
            password="testpass",
            store_session=False,
            timeout=5,
            token_path=token_path,
        )

        assert session.is_authenticated
        assert not token_path.exists()


class TestLogout:
    @responses.activate
    def test_logout_clears_state(self):
        """Logout should clear session and stored tokens."""
        # Login first
        responses.add(
            responses.POST,
            urls.LOGIN,
            json={
                "access_token": "token-to-clear",
                "token_type": "Bearer",
                "refresh_token": "refresh-to-clear",
                "expires_in": 86400,
            },
            status=200,
        )
        responses.add(
            responses.POST,
            urls.LOGOUT,
            json={},
            status=200,
        )

        token_path = Path("/tmp/hood-test-logout.json")
        login(
            username="test@example.com",
            password="testpass",
            timeout=5,
            token_path=token_path,
        )

        logout()

        with pytest.raises(AuthError, match="Not logged in"):
            get_session()

        assert not token_path.exists()


class TestGetSession:
    def test_no_session(self):
        """get_session without login should raise."""
        # Reset module state
        import hood.auth
        hood.auth._active_session = None
        with pytest.raises(AuthError, match="Not logged in"):
            get_session()
