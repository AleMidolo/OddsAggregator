# Shared Connector Runtime

Issue #2 implements the bookmaker-agnostic connector contract and the ingestion resilience primitives used by every provider adapter.

## Public connector boundary

Shared DTOs and the `BookmakerConnector` protocol live in `odds_aggregator.connectors`. Provider adapters must return these DTOs rather than raw provider classes. The DTO layer validates timezone-aware timestamps, positive decimal odds when a price is available, explicit availability/suspension state, and preserved source identifiers.

The shared error taxonomy distinguishes permanent authentication, authorization, schema, and configuration failures from transient timeout, unavailable, and rate-limit failures. Only transient failures are automatically retryable.

## Per-bookmaker resilience

`odds_aggregator.ingestion` provides a `ConnectorResilienceRegistry` and `ConnectorOperationExecutor`. A registry creates independent controls per bookmaker code:

- operation timeout and overall job deadline;
- concurrency semaphore;
- token-bucket rate limiter;
- bounded exponential retry with jitter;
- provider `Retry-After` precedence for rate-limit failures;
- circuit breaker for repeated timeout/unavailable failures.

Provider limits must come from the permitted integration contract or documentation. Do not configure these primitives to bypass provider controls.

External task cancellation is never swallowed. Unknown exceptions are isolated by `run_isolated_operations` and fail only the affected bookmaker operation.

## Metrics and outcomes

`odds_aggregator.observability` exposes connector operation metrics and typed run outcomes. Metrics include bookmaker code, operation, attempt, latency, rate-limit wait, retry scheduling, and terminal error type when applicable.

## Fixture connector

`FakeBookmakerConnector` is deterministic and contains no network I/O. It supports fixed DTO fixtures, operation delays, and explicit failure plans so contract and resilience tests can exercise retries, timeouts, rate limits, cancellation, suspension, and partial connector failure without live bookmaker services.

## Testing

The unit suite covers shared DTO invariants, typed error retry classification, Retry-After behavior, exponential retry, timeout translation, external cancellation, per-bookmaker circuit isolation, per-bookmaker concurrency/rate limiting, and independent connector failure.

CI remains fixture/mock-only and must not call live bookmaker services.
