"""Tests for the guided setup commands.

The security properties are the point of these tests: secrets must reach the
credentials file and nowhere else, files must be owner-only, and existing
credentials must not be silently replaced.
"""

import base64
import json
import stat
import time

import pytest

from pyhood import onboarding
from pyhood.crypto.credentials import API_KEY_VAR, PRIVATE_KEY_VAR


@pytest.fixture
def crypto_env(tmp_path, monkeypatch):
    """Point crypto credentials at a temp file, with a clean environment."""
    path = tmp_path / "crypto.env"
    monkeypatch.setenv("PYHOOD_CRYPTO_ENV", str(path))
    monkeypatch.delenv(API_KEY_VAR, raising=False)
    monkeypatch.delenv(PRIVATE_KEY_VAR, raising=False)
    return path


@pytest.fixture
def session_file(tmp_path, monkeypatch):
    """Point the session store at a temp directory."""
    monkeypatch.setattr("pyhood.auth.DEFAULT_TOKEN_DIR", tmp_path)
    monkeypatch.setattr("pyhood.auth.DEFAULT_TOKEN_FILE", "session.json")
    return tmp_path / "session.json"


class Recorder:
    """Collects printed lines."""

    def __init__(self):
        self.lines = []

    def __call__(self, line=""):
        self.lines.append(str(line))

    @property
    def text(self):
        return "\n".join(self.lines)


def write_creds(path, api_key="abc123", private_key=None):
    if private_key is None:
        private_key = base64.b64encode(b"k" * 32).decode()
    path.write_text(f"{API_KEY_VAR}={api_key}\n{PRIVATE_KEY_VAR}={private_key}\n")
    path.chmod(0o600)
    return private_key


class TestCryptoStatus:
    def test_reports_shape_not_values(self, crypto_env):
        private_key = write_creds(crypto_env, api_key="k" * 43)

        info = onboarding.crypto_status()

        assert info["source"] == "file"
        assert info["api_key_chars"] == 43
        assert info["private_key_bytes"] == 32
        assert info["private_key_valid"] is True
        # The values themselves are never part of the report.
        assert private_key not in json.dumps(info, default=str)
        assert "k" * 43 not in json.dumps(info, default=str)

    def test_detects_placeholder_credentials(self, crypto_env):
        """The failure that motivated this command: a pasted placeholder."""
        write_creds(crypto_env, api_key="your-key", private_key="your-private-key")

        info = onboarding.crypto_status()

        assert info["private_key_valid"] is False

    def test_short_but_valid_base64_is_rejected(self, crypto_env):
        write_creds(crypto_env, private_key=base64.b64encode(b"short").decode())

        info = onboarding.crypto_status()

        assert info["private_key_bytes"] == 5
        assert info["private_key_valid"] is False

    def test_missing_file(self, crypto_env):
        info = onboarding.crypto_status()

        assert info["source"] == "none"
        assert info["exists"] is False
        assert info["private_key_valid"] is False

    def test_environment_shadows_file(self, crypto_env, monkeypatch):
        write_creds(crypto_env)
        monkeypatch.setenv(API_KEY_VAR, "from-env")
        monkeypatch.setenv(PRIVATE_KEY_VAR, base64.b64encode(b"e" * 32).decode())

        assert onboarding.crypto_status()["source"] == "environment"


class TestSessionStatus:
    def test_reports_refreshability_and_age(self, session_file):
        session_file.write_text(json.dumps({
            "access_token": "secret-access",
            "token_type": "Bearer",
            "refresh_token": "secret-refresh",
            "device_token": "dev",
            "saved_at": time.time() - 7200,
        }))
        session_file.chmod(0o600)

        info = onboarding.session_status()

        assert info["exists"] is True
        assert info["has_refresh_token"] is True
        assert info["age_hours"] == pytest.approx(2.0, abs=0.1)
        assert info["owner_only"] is True
        assert "secret-access" not in json.dumps(info, default=str)
        assert "secret-refresh" not in json.dumps(info, default=str)

    def test_missing_file(self, session_file):
        assert onboarding.session_status()["exists"] is False

    def test_corrupt_file_does_not_raise(self, session_file):
        session_file.write_text("not json")

        info = onboarding.session_status()

        assert info["exists"] is True
        assert info["has_refresh_token"] is False

    def test_flags_world_readable_session(self, session_file):
        session_file.write_text(json.dumps({"refresh_token": "r", "saved_at": time.time()}))
        session_file.chmod(0o644)

        assert onboarding.session_status()["owner_only"] is False


class TestPrintStatus:
    def test_unconfigured_points_at_the_commands(self, crypto_env, session_file):
        out = Recorder()

        assert onboarding.print_status(out=out) == 1
        assert "python -m pyhood setup login" in out.text
        assert "python -m pyhood setup crypto" in out.text

    def test_configured_reports_success(self, crypto_env, session_file):
        write_creds(crypto_env)
        session_file.write_text(json.dumps({
            "refresh_token": "r", "saved_at": time.time(),
        }))
        session_file.chmod(0o600)
        out = Recorder()

        assert onboarding.print_status(out=out) == 0

    def test_warns_about_loose_permissions(self, crypto_env, session_file):
        write_creds(crypto_env)
        crypto_env.chmod(0o644)
        out = Recorder()

        onboarding.print_status(out=out)

        assert "chmod 600" in out.text

    def test_warns_when_environment_shadows_file(self, crypto_env, session_file, monkeypatch):
        write_creds(crypto_env)
        monkeypatch.setenv(API_KEY_VAR, "from-env")
        monkeypatch.setenv(PRIVATE_KEY_VAR, base64.b64encode(b"e" * 32).decode())
        out = Recorder()

        onboarding.print_status(out=out)

        assert "being ignored" in out.text


class TestSetupCrypto:
    def test_writes_owner_only_credentials(self, crypto_env):
        out = Recorder()

        code = onboarding.setup_crypto(
            verify=False, secret_prompt=lambda _: "issued-api-key", out=out,
        )

        assert code == 0
        assert stat.S_IMODE(crypto_env.stat().st_mode) == 0o600
        contents = crypto_env.read_text()
        assert f"{API_KEY_VAR}=issued-api-key" in contents
        assert PRIVATE_KEY_VAR in contents

    def test_private_key_is_never_printed(self, crypto_env):
        """The generated private key must reach the file and nothing else."""
        out = Recorder()

        onboarding.setup_crypto(
            verify=False, secret_prompt=lambda _: "issued-api-key", out=out,
        )

        stored = dict(
            line.split("=", 1) for line in crypto_env.read_text().splitlines() if line
        )
        private_key = stored[PRIVATE_KEY_VAR]
        assert private_key
        assert private_key not in out.text
        # The API key the user pasted is not echoed back either.
        assert "issued-api-key" not in out.text

    def test_public_key_is_printed(self, crypto_env):
        out = Recorder()

        onboarding.setup_crypto(
            verify=False, secret_prompt=lambda _: "issued-api-key", out=out,
        )

        assert onboarding.KEY_MANAGEMENT_URL in out.text
        # A base64 Ed25519 public key is 44 characters.
        assert any(len(word) == 44 for line in out.lines for word in line.split())

    def test_refuses_to_overwrite_without_force(self, crypto_env):
        original = crypto_env
        write_creds(original, api_key="existing-key")
        out = Recorder()

        code = onboarding.setup_crypto(
            verify=False, secret_prompt=lambda _: "new-key", out=out,
        )

        assert code == 1
        assert "existing-key" in crypto_env.read_text()
        assert "--force" in out.text

    def test_force_replaces(self, crypto_env):
        write_creds(crypto_env, api_key="existing-key")

        code = onboarding.setup_crypto(
            force=True, verify=False, secret_prompt=lambda _: "new-key", out=Recorder(),
        )

        assert code == 0
        assert "existing-key" not in crypto_env.read_text()

    def test_empty_input_saves_nothing(self, crypto_env):
        out = Recorder()

        code = onboarding.setup_crypto(
            verify=False, secret_prompt=lambda _: "  ", out=out,
        )

        assert code == 1
        assert not crypto_env.exists()

    def test_warns_when_environment_would_shadow_the_new_keys(self, crypto_env, monkeypatch):
        monkeypatch.setenv(API_KEY_VAR, "stale")
        monkeypatch.setenv(PRIVATE_KEY_VAR, "stale")
        out = Recorder()

        onboarding.setup_crypto(
            verify=False, secret_prompt=lambda _: "new-key", out=out,
        )

        assert "take precedence" in out.text

    def test_verification_failure_is_reported(self, crypto_env, monkeypatch):
        class Boom:
            def __init__(self, *a, **k):
                raise RuntimeError("Authentication failed")

        monkeypatch.setattr("pyhood.crypto.CryptoClient", Boom)
        out = Recorder()

        code = onboarding.setup_crypto(secret_prompt=lambda _: "new-key", out=out)

        assert code == 1
        assert "FAILED" in out.text
        # The keys are still on disk — the user only needs to register them.
        assert crypto_env.is_file()

    def test_verification_success(self, crypto_env, monkeypatch):
        class Account:
            status = "active"
            fee_tier = "1"

        class Client:
            def __init__(self, *a, **k):
                pass

            def get_account(self):
                return Account()

        monkeypatch.setattr("pyhood.crypto.CryptoClient", Client)
        out = Recorder()

        code = onboarding.setup_crypto(secret_prompt=lambda _: "new-key", out=out)

        assert code == 0
        assert "OK" in out.text


class TestSetupLogin:
    def test_reuses_a_working_session_without_prompting(self, session_file, monkeypatch):
        session_file.write_text(json.dumps({"refresh_token": "r", "saved_at": time.time()}))
        monkeypatch.setattr("pyhood.login", lambda *a, **k: object())

        def fail(_):
            raise AssertionError("should not prompt when the session works")

        out = Recorder()
        code = onboarding.setup_login(prompt=fail, secret_prompt=fail, out=out)

        assert code == 0
        assert "Nothing else to do" in out.text

    def test_falls_back_to_a_full_login(self, session_file, monkeypatch):
        session_file.write_text(json.dumps({"refresh_token": "r", "saved_at": time.time()}))
        calls = []

        def fake_login(username=None, password=None, **kwargs):
            if username is None:
                raise RuntimeError("cached session dead")
            calls.append((username, password))
            return object()

        monkeypatch.setattr("pyhood.login", fake_login)
        out = Recorder()

        code = onboarding.setup_login(
            prompt=lambda _: "me@example.com",
            secret_prompt=lambda _: "hunter2",
            out=out,
        )

        assert code == 0
        assert calls == [("me@example.com", "hunter2")]

    def test_password_is_not_echoed(self, session_file, monkeypatch):
        monkeypatch.setattr("pyhood.login", lambda *a, **k: object())
        out = Recorder()

        onboarding.setup_login(
            prompt=lambda _: "me@example.com",
            secret_prompt=lambda _: "hunter2",
            out=out,
        )

        assert "hunter2" not in out.text

    def test_mfa_is_requested_and_retried(self, session_file, monkeypatch):
        from pyhood.exceptions import MFARequiredError

        attempts = []

        def fake_login(username=None, password=None, mfa_code=None, **kwargs):
            attempts.append(mfa_code)
            if mfa_code is None:
                raise MFARequiredError("mfa required")
            return object()

        monkeypatch.setattr("pyhood.login", fake_login)

        code = onboarding.setup_login(
            prompt=lambda p: "123456" if "MFA" in p else "me@example.com",
            secret_prompt=lambda _: "hunter2",
            out=Recorder(),
        )

        assert code == 0
        assert attempts == [None, "123456"]

    def test_auth_failure_returns_nonzero(self, session_file, monkeypatch):
        from pyhood.exceptions import AuthError

        def fake_login(*a, **k):
            raise AuthError("bad credentials")

        monkeypatch.setattr("pyhood.login", fake_login)
        out = Recorder()

        code = onboarding.setup_login(
            prompt=lambda _: "me@example.com",
            secret_prompt=lambda _: "wrong",
            out=out,
        )

        assert code == 1
        assert "FAILED" in out.text

    def test_empty_username_attempts_nothing(self, session_file, monkeypatch):
        def fail(*a, **k):
            raise AssertionError("should not log in")

        monkeypatch.setattr("pyhood.login", fail)

        code = onboarding.setup_login(
            prompt=lambda _: "", secret_prompt=fail, out=Recorder(),
        )

        assert code == 1


class TestCommandLine:
    def test_no_arguments_prints_help(self, capsys):
        assert onboarding.main([]) == 0
        assert "setup" in capsys.readouterr().out

    def test_setup_without_target_reports_status(self, monkeypatch):
        called = []
        monkeypatch.setattr(onboarding, "print_status", lambda: called.append(True) or 0)

        assert onboarding.main(["setup"]) == 0
        assert called

    def test_setup_crypto_routes_with_flags(self, monkeypatch):
        seen = {}

        def fake(force, verify):
            seen.update(force=force, verify=verify)
            return 0

        monkeypatch.setattr(onboarding, "setup_crypto", fake)

        assert onboarding.main(["setup", "crypto", "--force", "--no-verify"]) == 0
        assert seen == {"force": True, "verify": False}

    def test_setup_login_routes(self, monkeypatch):
        monkeypatch.setattr(onboarding, "setup_login", lambda: 0)

        assert onboarding.main(["setup", "login"]) == 0

    def test_rejects_unknown_target(self):
        with pytest.raises(SystemExit):
            onboarding.main(["setup", "nonsense"])

    def test_no_option_accepts_a_secret(self):
        """Secrets must never be passable as arguments — argv is world-visible."""
        parser = onboarding.build_parser()
        actions = [a for a in parser._subparsers._group_actions[0].choices["setup"]._actions]
        flags = {opt for a in actions for opt in a.option_strings}

        for leaky in ("--api-key", "--password", "--private-key", "--token"):
            assert leaky not in flags


class TestCancellation:
    """Ctrl-C at a prompt must exit cleanly, not raise through to a traceback."""

    def _interrupt(self, _):
        raise KeyboardInterrupt

    def test_crypto_cancelled_saves_nothing(self, crypto_env):
        out = Recorder()

        code = onboarding.setup_crypto(verify=False, secret_prompt=self._interrupt, out=out)

        assert code == 1
        assert not crypto_env.exists()
        assert "Cancelled" in out.text

    def test_login_cancelled_at_username(self, session_file, monkeypatch):
        monkeypatch.setattr("pyhood.login", lambda *a, **k: pytest.fail("should not log in"))
        out = Recorder()

        code = onboarding.setup_login(
            prompt=self._interrupt, secret_prompt=self._interrupt, out=out,
        )

        assert code == 1
        assert "Cancelled" in out.text

    def test_login_cancelled_at_password(self, session_file, monkeypatch):
        monkeypatch.setattr("pyhood.login", lambda *a, **k: pytest.fail("should not log in"))
        out = Recorder()

        code = onboarding.setup_login(
            prompt=lambda _: "me@example.com", secret_prompt=self._interrupt, out=out,
        )

        assert code == 1
        assert "Cancelled" in out.text

    def test_eof_is_treated_as_cancellation(self, crypto_env):
        def eof(_):
            raise EOFError

        out = Recorder()

        assert onboarding.setup_crypto(verify=False, secret_prompt=eof, out=out) == 1
        assert "Cancelled" in out.text


class TestVersionCommand:
    def test_version_subcommand(self, capsys):
        from pyhood import __version__

        assert onboarding.main(["version"]) == 0
        assert capsys.readouterr().out.strip() == f"pyhood {__version__}"

    def test_version_flag(self, capsys):
        from pyhood import __version__

        with pytest.raises(SystemExit) as exc:
            onboarding.main(["--version"])

        assert exc.value.code == 0
        assert capsys.readouterr().out.strip() == f"pyhood {__version__}"


class TestInvocation:
    """Suggested commands should match how the user actually invoked pyhood."""

    def test_console_script(self, monkeypatch):
        monkeypatch.setattr(onboarding.sys, "argv", ["/usr/local/bin/pyhood", "setup"])

        assert onboarding.invocation() == "pyhood"

    def test_module(self, monkeypatch):
        monkeypatch.setattr(onboarding.sys, "argv", ["/path/to/pyhood/__main__.py"])

        assert onboarding.invocation() == "python -m pyhood"

    def test_hints_follow_invocation(self, crypto_env, session_file, monkeypatch):
        monkeypatch.setattr(onboarding.sys, "argv", ["/usr/local/bin/pyhood"])
        out = Recorder()

        onboarding.print_status(out=out)

        assert "run: pyhood setup login" in out.text
        assert "python -m pyhood" not in out.text
