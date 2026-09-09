from odds_aggregator.connectors import (
    ConnectorAuthenticationError,
    ConnectorAuthorizationError,
    ConnectorConfigurationError,
    ConnectorRateLimitedError,
    ConnectorSchemaError,
    ConnectorTimeoutError,
    ConnectorUnavailableError,
    is_retryable_connector_error,
)


def test_only_transient_connector_errors_are_retryable() -> None:
    assert is_retryable_connector_error(ConnectorRateLimitedError("slow down"))
    assert is_retryable_connector_error(ConnectorTimeoutError("timed out"))
    assert is_retryable_connector_error(ConnectorUnavailableError("unavailable"))

    assert not is_retryable_connector_error(ConnectorAuthenticationError("bad credentials"))
    assert not is_retryable_connector_error(ConnectorAuthorizationError("forbidden"))
    assert not is_retryable_connector_error(ConnectorSchemaError("bad schema"))
    assert not is_retryable_connector_error(ConnectorConfigurationError("bad config"))
