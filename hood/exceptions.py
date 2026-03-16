"""hood exceptions — clear error types instead of silent failures."""


class HoodError(Exception):
    """Base exception for all hood errors."""


class AuthError(HoodError):
    """Authentication failed."""


class LoginTimeoutError(AuthError):
    """Login hung — likely waiting for device approval."""


LoginTimeout = LoginTimeoutError  # convenience alias


class TokenExpiredError(AuthError):
    """Stored session token has expired."""


TokenExpired = TokenExpiredError  # convenience alias


class DeviceApprovalRequiredError(AuthError):
    """Robinhood is requesting device approval via the mobile app."""


DeviceApprovalRequired = DeviceApprovalRequiredError  # convenience alias


class MFARequiredError(AuthError):
    """Multi-factor authentication code required."""


MFARequired = MFARequiredError  # convenience alias


class RateLimitError(HoodError):
    """Too many requests — slow down."""

    def __init__(self, message: str = "Rate limited", retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class APIError(HoodError):
    """Robinhood API returned an error."""

    def __init__(self, message: str, status_code: int | None = None, response: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class OrderError(HoodError):
    """Order placement or modification failed."""


class SymbolNotFoundError(HoodError):
    """Ticker symbol not recognized."""


SymbolNotFound = SymbolNotFoundError  # convenience alias
