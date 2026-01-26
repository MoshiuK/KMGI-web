"""
Custom exceptions for the Vimeo to Roku SDK.
"""


class VimeoRokuSDKError(Exception):
    """Base exception for all SDK errors."""
    pass


class VimeoAPIError(VimeoRokuSDKError):
    """Error communicating with the Vimeo API."""

    def __init__(self, message: str, status_code: int = None, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class VimeoAuthError(VimeoAPIError):
    """Authentication error with Vimeo API."""
    pass


class VimeoRateLimitError(VimeoAPIError):
    """Rate limit exceeded on Vimeo API."""

    def __init__(self, message: str, retry_after: int = None):
        super().__init__(message)
        self.retry_after = retry_after


class RokuFeedError(VimeoRokuSDKError):
    """Error generating Roku feed."""
    pass


class RokuValidationError(RokuFeedError):
    """Roku feed validation error."""

    def __init__(self, message: str, errors: list = None):
        super().__init__(message)
        self.errors = errors or []


class ConfigurationError(VimeoRokuSDKError):
    """Configuration error."""
    pass


class SyncError(VimeoRokuSDKError):
    """Error during sync operation."""
    pass
