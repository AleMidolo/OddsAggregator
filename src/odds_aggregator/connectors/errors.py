"""Shared connector failure taxonomy."""

from __future__ import annotations

from typing import ClassVar


class ConnectorError(Exception):
    """Base class for connector failures understood by ingestion policy."""

    retryable: ClassVar[bool] = False

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ConnectorAuthenticationError(ConnectorError):
    pass


class ConnectorAuthorizationError(ConnectorError):
    pass


class ConnectorRateLimitedError(ConnectorError):
    retryable = True


class ConnectorTimeoutError(ConnectorError):
    retryable = True


class ConnectorUnavailableError(ConnectorError):
    retryable = True


class ConnectorSchemaError(ConnectorError):
    pass


class ConnectorConfigurationError(ConnectorError):
    pass


class ConnectorCircuitOpenError(ConnectorError):
    pass


def is_retryable_connector_error(error: ConnectorError) -> bool:
    return error.retryable
