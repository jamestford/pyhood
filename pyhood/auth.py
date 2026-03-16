"""Authentication — login, logout, token management.

Rebuilt from robin_stocks' auth with:
- Configurable timeouts (no more infinite hangs)
- Clear exception types for each failure mode
- Automatic token refresh before expiry
- Persistent device token (avoids re-verification)
"""

from __future__ import annotations

import json
import logging
import secrets
import signal
import time
from pathlib import Path
from typing import Any

from pyhood import urls
from pyhood.exceptions import (
    AuthError,
    DeviceApprovalRequired,
    LoginTimeout,
    MFARequired,
    RateLimitError,
)
from pyhood.http import Session

logger = logging.getLogger("pyhood")

# Robinhood's public OAuth client ID
CLIENT_ID = "c82SH0WZOsabOXGP2sxqcj34FxkvfnWRZBKlBjFS"

# Default token storage
DEFAULT_TOKEN_DIR = Path.home() / ".pyhood"
DEFAULT_TOKEN_FILE = "session.json"


def generate_device_token() -> str:
    """Generate a cryptographically secure device token in Robinhood's expected format."""
    rands = [secrets.randbelow(256) for _ in range(16)]
    hexa = [format(i, "02x") for i in range(256)]
    token = ""
    for i, r in enumerate(rands):
        token += hexa[r]
        if i in (3, 5, 7, 9):
            token += "-"
    return token


class TokenStore:
    """Manages token persistence on disk.

    Stored data:
    - access_token, token_type, refresh_token: OAuth tokens
    - device_token: Persistent device ID (reuse avoids re-verification)
    - saved_at: Timestamp when tokens were saved
    """

    def __init__(self, path: Path | None = None):
        self.path = path or (DEFAULT_TOKEN_DIR / DEFAULT_TOKEN_FILE)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any] | None:
        """Load stored tokens. Returns None if no file or corrupt."""
        if not self.path.is_file():
            return None
        try:
            with open(self.path) as f:
                data = json.load(f)
            # Validate required fields
            required = ("access_token", "token_type", "refresh_token", "device_token")
            if not all(k in data for k in required):
                logger.warning("Token file missing required fields, ignoring")
                return None
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load token file: {e}")
            return None

    def save(
        self,
        access_token: str,
        token_type: str,
        refresh_token: str,
        device_token: str,
    ) -> None:
        """Save tokens to disk."""
        data = {
            "access_token": access_token,
            "token_type": token_type,
            "refresh_token": refresh_token,
            "device_token": device_token,
            "saved_at": time.time(),
        }
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)
        logger.debug(f"Tokens saved to {self.path}")

    def clear(self) -> None:
        """Remove stored tokens."""
        if self.path.is_file():
            self.path.unlink()
            logger.debug("Token file removed")

    @property
    def device_token(self) -> str | None:
        """Get the stored device token without loading full session."""
        data = self.load()
        return data.get("device_token") if data else None


def _handle_verification(
    session: Session,
    device_token: str,
    workflow_id: str,
    timeout: float,
) -> None:
    """Handle Robinhood's device verification workflow.

    Supports:
    - App push approval (most common)
    - SMS / email code verification
    - Raises DeviceApprovalRequired with clear instructions
    """
    logger.info("Verification required, handling challenge...")

    pathfinder_url = "https://api.robinhood.com/pathfinder/user_machine/"
    machine_payload = {
        "device_id": device_token,
        "flow": "suv",
        "input": {"workflow_id": workflow_id},
    }
    machine_data = session.post(pathfinder_url, json_data=machine_payload)

    machine_id = machine_data.get("id")
    if not machine_id:
        raise AuthError("No verification ID returned from Robinhood")

    inquiries_url = f"https://api.robinhood.com/pathfinder/inquiries/{machine_id}/user_view/"
    start_time = time.monotonic()

    while time.monotonic() - start_time < timeout:
        time.sleep(8)
        try:
            inquiries_response = session.get(inquiries_url)
        except RateLimitError:
            logger.warning("Rate limited during verification polling, waiting...")
            time.sleep(10)
            continue
        except Exception:
            continue

        if not inquiries_response:
            continue

        context = inquiries_response.get("context", {})
        challenge = context.get("sheriff_challenge", {})

        if not challenge:
            continue

        challenge_type = challenge.get("type")
        challenge_status = challenge.get("status")
        challenge_id = challenge.get("id")

        if challenge_type == "prompt":
            logger.info("Device approval required — check Robinhood app")
            prompt_url = f"https://api.robinhood.com/push/{challenge_id}/get_prompts_status/"
            poll_delay = 10  # Start with 10s between polls

            while time.monotonic() - start_time < timeout:
                time.sleep(poll_delay)
                try:
                    prompt_status = session.get(prompt_url)
                    if prompt_status.get("challenge_status") == "validated":
                        logger.info("Device approved via app")
                        break
                    # Reset delay on success
                    poll_delay = 10
                except RateLimitError as e:
                    # Back off more aggressively
                    poll_delay = min(poll_delay + 5, 30)
                    retry_wait = e.retry_after or poll_delay
                    logger.warning(f"Rate limited, backing off to {retry_wait}s")
                    time.sleep(retry_wait)
                    continue
                except Exception as e:
                    logger.warning(f"Poll error: {e}, retrying...")
                    time.sleep(poll_delay)
                    continue
            else:
                raise DeviceApprovalRequired(
                    "Timed out waiting for device approval. "
                    "Open the Robinhood app and approve the login request."
                )
            break

        if challenge_status == "validated":
            logger.info("Verification successful")
            break

        if challenge_type in ("sms", "email") and challenge_status == "issued":
            raise MFARequired(
                f"Robinhood sent a verification code via {challenge_type}. "
                f"Re-login with mfa_code parameter."
            )

    # Poll workflow status for final approval
    retry_attempts = 5
    while time.monotonic() - start_time < timeout and retry_attempts > 0:
        try:
            inquiries_payload = {"sequence": 0, "user_input": {"status": "continue"}}
            resp = session.post(
                inquiries_url,
                json_data=inquiries_payload,
                accept_codes=(400, 401, 402, 403),
            )

            type_context = resp.get("type_context", {})
            if type_context.get("result") == "workflow_status_approved":
                logger.info("Workflow approved")
                return

            workflow_status = resp.get("verification_workflow", {}).get("workflow_status")
            if workflow_status == "workflow_status_approved":
                logger.info("Workflow approved")
                return

            time.sleep(5)
        except Exception as e:
            logger.warning(f"Verification poll failed: {e}")
            retry_attempts -= 1
            time.sleep(5)

    # If we get here, assume approved (matches robin_stocks behavior)
    logger.warning("Verification timeout — proceeding (may fail)")


# Module-level state for the convenience API
_active_session: Session | None = None
_active_store: TokenStore | None = None


def login(
    username: str | None = None,
    password: str | None = None,
    mfa_code: str | None = None,
    timeout: float = 60,
    store_session: bool = True,
    token_path: Path | str | None = None,
    expires_in: int = 86400,
) -> Session:
    """Log in to Robinhood.

    Args:
        username: Robinhood email/username.
        password: Robinhood password.
        mfa_code: MFA code if required (SMS/email/TOTP).
        timeout: Max seconds to wait for login (including device approval).
            Set to 0 to disable timeout. Default: 60s.
        store_session: Cache tokens to disk for reuse. Default: True.
        token_path: Custom path for token storage. Default: ~/.pyhood/session.json.
        expires_in: Token lifetime in seconds. Default: 86400 (24h).

    Returns:
        Authenticated Session object.

    Raises:
        LoginTimeout: Login hung (likely device approval timeout).
        DeviceApprovalRequired: Robinhood wants app approval.
        MFARequired: Need to provide mfa_code.
        TokenExpired: Stored token expired, re-login needed.
        AuthError: Generic auth failure.
    """
    global _active_session, _active_store

    session = Session()
    store = TokenStore(Path(token_path) if token_path else None)

    # Try cached session first
    if store_session:
        cached = store.load()
        if cached:
            logger.info("Found cached session, validating...")
            session.set_auth(cached["token_type"], cached["access_token"])
            try:
                session.get(urls.POSITIONS, params={"nonzero": "true"})
                logger.info("Cached session is valid")
                _active_session = session
                _active_store = store
                return session
            except Exception:
                logger.info("Cached session expired, trying refresh...")
                session.clear_auth()

                # Try refresh before falling back to full re-login
                if cached.get("refresh_token"):
                    try:
                        return refresh(token_path=token_path, timeout=timeout)
                    except Exception as refresh_err:
                        logger.info(f"Refresh failed ({refresh_err}), falling back to full login")

    # Need credentials for fresh login
    if not username or not password:
        raise AuthError("Username and password required (cached session expired or not found)")

    # Reuse stored device token to avoid re-verification when possible
    device_token = (store.device_token if store_session else None) or generate_device_token()

    login_payload = {
        "client_id": CLIENT_ID,
        "expires_in": expires_in,
        "grant_type": "password",
        "password": password,
        "scope": "internal",
        "username": username,
        "device_token": device_token,
        "try_passkeys": False,
        "token_request_path": "/login",
        "create_read_only_secondary_token": True,
    }

    if mfa_code:
        login_payload["mfa_code"] = mfa_code

    # Set timeout alarm (Unix only)
    original_handler = None
    if timeout > 0:
        def _timeout_handler(signum, frame):
            raise LoginTimeout(
                f"Login timed out after {timeout}s. "
                "Robinhood may be waiting for device approval — check the Robinhood app."
            )
        original_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(int(timeout))

    try:
        # Robinhood login returns 400/403 with valid JSON (verification data)
        login_accept = (400, 401, 402, 403)
        data = session.post(urls.LOGIN, data=login_payload, accept_codes=login_accept)

        if not data:
            raise AuthError("Empty response from Robinhood login endpoint")

        # Handle verification workflow
        if "verification_workflow" in data:
            workflow_id = data["verification_workflow"]["id"]
            _handle_verification(session, device_token, workflow_id, timeout)
            # Re-attempt login after verification
            data = session.post(urls.LOGIN, data=login_payload, accept_codes=login_accept)

        if "access_token" not in data:
            raise AuthError(f"Login failed — unexpected response: {list(data.keys())}")

        # Set auth on session
        session.set_auth(data["token_type"], data["access_token"])

        # Persist tokens
        if store_session:
            store.save(
                access_token=data["access_token"],
                token_type=data["token_type"],
                refresh_token=data["refresh_token"],
                device_token=device_token,
            )

        _active_session = session
        _active_store = store
        logger.info("Login successful")
        return session

    finally:
        # Clear alarm
        if timeout > 0:
            signal.alarm(0)
            if original_handler is not None:
                signal.signal(signal.SIGALRM, original_handler)


def refresh(
    token_path: Path | str | None = None,
    timeout: float = 30,
) -> Session:
    """Refresh the session using the stored refresh token.

    This avoids a full re-login and does NOT require device approval.
    The refresh token is exchanged for a new access_token + refresh_token pair.

    Args:
        token_path: Custom path for token storage. Default: ~/.pyhood/session.json.
        timeout: Max seconds to wait. Default: 30s.

    Returns:
        Authenticated Session object with new tokens.

    Raises:
        AuthError: No stored session or refresh token.
        TokenExpired: Refresh token has expired (full re-login needed).
    """
    global _active_session, _active_store

    store = TokenStore(Path(token_path) if token_path else None)
    cached = store.load()

    if not cached or not cached.get("refresh_token"):
        raise AuthError("No refresh token available. Call hood.login() first.")

    session = Session(timeout=timeout)
    device_token = cached.get("device_token", "")

    refresh_payload = {
        "grant_type": "refresh_token",
        "refresh_token": cached["refresh_token"],
        "scope": "internal",
        "client_id": CLIENT_ID,
        "device_token": device_token,
        "expires_in": 86400,
    }

    logger.info("Refreshing session with refresh token...")

    try:
        data = session.post(
            urls.LOGIN,
            data=refresh_payload,
            accept_codes=(400, 401, 403),
        )
    except Exception as e:
        raise AuthError(f"Refresh request failed: {e}") from e

    if not data:
        raise AuthError("Empty response from refresh endpoint")

    # If Robinhood demands verification, the refresh token may be expired
    if "verification_workflow" in data:
        from pyhood.exceptions import TokenExpiredError
        raise TokenExpiredError(
            "Refresh token expired — Robinhood is requesting device approval. "
            "Call hood.login() with username and password."
        )

    if "access_token" not in data:
        raise AuthError(f"Refresh failed — unexpected response: {list(data.keys())}")

    # Set auth on session
    session.set_auth(data["token_type"], data["access_token"])

    # Persist new tokens (refresh tokens rotate — save the new one)
    store.save(
        access_token=data["access_token"],
        token_type=data["token_type"],
        refresh_token=data["refresh_token"],
        device_token=device_token,
    )

    _active_session = session
    _active_store = store
    logger.info("Session refreshed successfully")
    return session


def logout() -> None:
    """Log out and clear stored session."""
    global _active_session, _active_store
    if _active_session and _active_session.is_authenticated:
        try:
            _active_session.post(urls.LOGOUT, data={
                "client_id": CLIENT_ID,
                "token": "",  # Robinhood doesn't actually require the token here
            })
        except Exception:
            pass  # Best-effort
    if _active_session:
        _active_session.clear_auth()
    if _active_store:
        _active_store.clear()
    _active_session = None
    _active_store = None
    logger.info("Logged out")


def get_session() -> Session:
    """Get the active authenticated session. Raises if not logged in."""
    if _active_session is None or not _active_session.is_authenticated:
        raise AuthError("Not logged in. Call hood.login() first.")
    return _active_session
