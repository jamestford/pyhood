"""Tests for crypto authentication module."""

import base64
import time

import nacl.signing
import pytest

from pyhood.crypto.auth import generate_keypair, sign_request


class TestCryptoAuth:
    """Test crypto authentication functions."""

    def test_generate_keypair(self):
        """Test keypair generation returns valid base64 keys."""
        private_key, public_key = generate_keypair()

        assert isinstance(private_key, str)
        assert isinstance(public_key, str)

        # Should be decodable base64
        private_bytes = base64.b64decode(private_key)
        public_bytes = base64.b64decode(public_key)

        # ED25519 keys are 32 bytes
        assert len(private_bytes) == 32
        assert len(public_bytes) == 32

    def test_generate_keypair_unique(self):
        """Each call generates different keys."""
        key1 = generate_keypair()
        key2 = generate_keypair()
        assert key1[0] != key2[0]

    def test_sign_request_returns_three_headers(self):
        """sign_request returns api_key, signature, and timestamp."""
        private_key, _ = generate_keypair()

        api_key_header, signature, timestamp = sign_request(
            api_key="test-key",
            private_key_base64=private_key,
            method="GET",
            path="/api/v2/crypto/trading/accounts/",
        )

        assert api_key_header == "test-key"
        assert isinstance(signature, str)
        assert len(signature) > 0
        assert isinstance(timestamp, str)
        assert timestamp.isdigit()

    def test_sign_request_signature_is_valid_base64(self):
        """Signature should be valid base64."""
        private_key, _ = generate_keypair()

        _, signature, _ = sign_request(
            api_key="test-key",
            private_key_base64=private_key,
            method="GET",
            path="/test/",
        )

        # Should decode without error
        sig_bytes = base64.b64decode(signature)
        # ED25519 signatures are 64 bytes
        assert len(sig_bytes) == 64

    def test_sign_request_deterministic(self):
        """Same inputs + same timestamp = same signature."""
        private_key, _ = generate_keypair()

        original_time = time.time
        time.time = lambda: 1700000000

        try:
            _, sig1, _ = sign_request(
                api_key="test-key",
                private_key_base64=private_key,
                method="GET",
                path="/test/",
            )
            _, sig2, _ = sign_request(
                api_key="test-key",
                private_key_base64=private_key,
                method="GET",
                path="/test/",
            )
            assert sig1 == sig2
        finally:
            time.time = original_time

    def test_sign_request_different_with_body(self):
        """Adding a body changes the signature."""
        private_key, _ = generate_keypair()

        original_time = time.time
        time.time = lambda: 1700000000

        try:
            _, sig_no_body, _ = sign_request(
                api_key="test-key",
                private_key_base64=private_key,
                method="POST",
                path="/test/",
            )
            _, sig_with_body, _ = sign_request(
                api_key="test-key",
                private_key_base64=private_key,
                method="POST",
                path="/test/",
                body='{"key": "value"}',
            )
            assert sig_no_body != sig_with_body
        finally:
            time.time = original_time

    def test_sign_request_verifiable(self):
        """Signature can be verified with the public key."""
        private_key, public_key = generate_keypair()
        api_key = "rh-api-test-key"

        original_time = time.time
        time.time = lambda: 1700000000

        try:
            _, signature, timestamp = sign_request(
                api_key=api_key,
                private_key_base64=private_key,
                method="POST",
                path="/api/v2/crypto/trading/orders/",
                body='{"symbol":"BTC-USD"}',
            )

            # Reconstruct the message
            message = (
                f"{api_key}{timestamp}/api/v2/crypto/trading/orders/POST"
                + '{"symbol":"BTC-USD"}'
            )

            # Verify with public key
            verify_key = nacl.signing.VerifyKey(base64.b64decode(public_key))
            sig_bytes = base64.b64decode(signature)
            verify_key.verify(message.encode("utf-8"), sig_bytes)  # Raises if invalid
        finally:
            time.time = original_time

    def test_sign_request_invalid_key(self):
        """Signing with invalid private key raises ValueError."""
        with pytest.raises(ValueError, match="Failed to sign request"):
            sign_request(
                api_key="test-key",
                private_key_base64="invalid-not-base64!!!",
                method="GET",
                path="/test",
            )

    def test_sign_request_wrong_length_key(self):
        """Signing with wrong-length key raises ValueError."""
        short_key = base64.b64encode(b"too-short").decode()
        with pytest.raises(ValueError, match="Failed to sign request"):
            sign_request(
                api_key="test-key",
                private_key_base64=short_key,
                method="GET",
                path="/test",
            )
