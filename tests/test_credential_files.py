"""Credential files must be owner-only, and crypto credentials resolvable.

~/.pyhood/session.json holds live access and refresh tokens. It was being
written with the process umask, which on a default macOS setup produced
-rw-r--r-- — readable by every user on the machine.
"""

import json
import os
import stat

import pytest

from pyhood.auth import TokenStore
from pyhood.crypto.credentials import (
    API_KEY_VAR,
    PRIVATE_KEY_VAR,
    credentials_available,
    load_credentials,
)
from pyhood.secure_files import warn_if_readable_by_others, write_private


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


class TestSecureWrites:
    def test_written_file_is_owner_only(self, tmp_path):
        target = tmp_path / "nested" / "secret.json"

        write_private(target, '{"token": "x"}')

        assert _mode(target) == 0o600
        assert _mode(target.parent) == 0o700
        assert target.read_text() == '{"token": "x"}'

    def test_existing_loose_file_is_tightened(self, tmp_path):
        target = tmp_path / "secret.json"
        target.write_text("old")
        os.chmod(target, 0o644)

        write_private(target, "new")

        assert _mode(target) == 0o600
        assert target.read_text() == "new"

    def test_warns_only_when_others_can_read(self, tmp_path, caplog):
        target = tmp_path / "s.json"
        target.write_text("x")

        os.chmod(target, 0o600)
        assert warn_if_readable_by_others(target) is False

        os.chmod(target, 0o644)
        assert warn_if_readable_by_others(target) is True


class TestTokenStorePermissions:
    def test_saved_session_is_owner_only(self, tmp_path):
        store = TokenStore(tmp_path / "session.json")

        store.save("access", "Bearer", "refresh", "device")

        assert _mode(store.path) == 0o600
        assert json.loads(store.path.read_text())["access_token"] == "access"


class TestCryptoCredentials:
    def test_explicit_values_win(self):
        assert load_credentials("k", "p") == ("k", "p")

    def test_reads_environment(self, monkeypatch):
        monkeypatch.setenv(API_KEY_VAR, "env-key")
        monkeypatch.setenv(PRIVATE_KEY_VAR, "env-priv")

        assert load_credentials() == ("env-key", "env-priv")

    def test_reads_env_file_when_environment_empty(self, monkeypatch, tmp_path):
        monkeypatch.delenv(API_KEY_VAR, raising=False)
        monkeypatch.delenv(PRIVATE_KEY_VAR, raising=False)
        f = tmp_path / "crypto.env"
        f.write_text(
            f"# comment\n{API_KEY_VAR}=file-key\n\n{PRIVATE_KEY_VAR}='file-priv'\n"
        )
        monkeypatch.setenv("PYHOOD_CRYPTO_ENV", str(f))

        assert load_credentials() == ("file-key", "file-priv")

    def test_missing_credentials_raise_with_guidance(self, monkeypatch, tmp_path):
        monkeypatch.delenv(API_KEY_VAR, raising=False)
        monkeypatch.delenv(PRIVATE_KEY_VAR, raising=False)
        monkeypatch.setenv("PYHOOD_CRYPTO_ENV", str(tmp_path / "absent.env"))

        with pytest.raises(FileNotFoundError, match="No crypto credentials"):
            load_credentials()
        assert credentials_available() is False
