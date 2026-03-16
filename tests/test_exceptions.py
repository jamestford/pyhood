"""Tests for exception hierarchy and attributes."""

from pyhood.exceptions import (
    APIError,
    AuthError,
    DeviceApprovalRequired,
    DeviceApprovalRequiredError,
    HoodError,
    LoginTimeout,
    LoginTimeoutError,
    MFARequired,
    MFARequiredError,
    OrderError,
    RateLimitError,
    SymbolNotFound,
    SymbolNotFoundError,
    TokenExpired,
    TokenExpiredError,
)


def test_hierarchy():
    """All exceptions inherit from HoodError."""
    assert issubclass(AuthError, HoodError)
    assert issubclass(LoginTimeoutError, AuthError)
    assert issubclass(TokenExpiredError, AuthError)
    assert issubclass(DeviceApprovalRequiredError, AuthError)
    assert issubclass(MFARequiredError, AuthError)
    assert issubclass(RateLimitError, HoodError)
    assert issubclass(APIError, HoodError)
    assert issubclass(OrderError, HoodError)
    assert issubclass(SymbolNotFoundError, HoodError)


def test_aliases():
    """Convenience aliases point to the right classes."""
    assert LoginTimeout is LoginTimeoutError
    assert TokenExpired is TokenExpiredError
    assert DeviceApprovalRequired is DeviceApprovalRequiredError
    assert MFARequired is MFARequiredError
    assert SymbolNotFound is SymbolNotFoundError


def test_api_error_attributes():
    err = APIError("test error", status_code=400, response={"detail": "bad request"})
    assert str(err) == "test error"
    assert err.status_code == 400
    assert err.response == {"detail": "bad request"}


def test_rate_limit_retry_after():
    err = RateLimitError("slow down", retry_after=5.0)
    assert err.retry_after == 5.0


def test_rate_limit_default():
    err = RateLimitError()
    assert err.retry_after is None


def test_exceptions_catchable_as_hood_error():
    """All can be caught with except HoodError."""
    for exc_class in [
        AuthError, LoginTimeoutError, TokenExpiredError,
        DeviceApprovalRequiredError, MFARequiredError,
        RateLimitError, APIError, OrderError, SymbolNotFoundError,
    ]:
        try:
            raise exc_class("test")
        except HoodError:
            pass  # Expected
