# Bookmaker Integration Architecture

## Purpose

Each bookmaker is isolated behind a common adapter contract. The core application must never import or depend on bookmaker-specific response models, URLs, authentication mechanisms, or provider naming conventions.

Only permitted integration methods may be used: official APIs, documented/licensed feeds, or publicly accessible endpoints whose terms allow automated access. Do not bypass CAPTCHAs, authentication, anti-bot systems, rate limits, geo-restrictions, or other access controls.

## Adapter responsibilities

A bookmaker adapter owns:
- permitted endpoint/feed access;
- authentication and request signing where legitimately provided;
- provider pagination;
- provider-specific throttling headers and limits;
- raw payload validation;
- source identifier extraction;
- conversion of source odds into decimal odds;
- mapping provider statuses into connector DTO status values;
- retaining enough source metadata for traceability and diagnostics.

An adapter does not own:
- canonical event identity;
- canonical participant identity;
- cross-bookmaker event matching;
- canonical market matching;
- persistence schema;
- arbitrage detection;
- application-wide scheduling policy.

## Connector interface

The first implementation should expose an async contract similar to:

```python
class BookmakerConnector(Protocol):
    bookmaker_code: str

    async def health(self) -> ConnectorHealth: ...
    async def list_sports(self) -> list[SourceSport]: ...
    async def list_events(self, request: EventFeedRequest) -> EventFeedResult: ...
    async def get_markets(self, request: MarketFeedRequest) -> MarketFeedResult: ...
```

The precise Python signatures may evolve, but these rules are mandatory:

1. return connector DTOs, never raw provider response classes;
2. all network operations are async;
3. every request is externally cancellable and has a timeout;
4. pagination is contained within or explicitly represented by the connector API;
5. errors use a shared typed error taxonomy;
6. no adapter writes directly to canonical persistence;
7. connector DTOs preserve source IDs.

## Connector DTOs

Initial shared DTO concepts:
- `SourceSport`
- `SourceCompetition`
- `SourceParticipant`
- `SourceEvent`
- `SourceMarket`
- `SourceSelection`
- `SourcePrice`

DTOs should contain normalized primitive types and provider source identifiers. They may retain a bounded `metadata` mapping only for source attributes that have not yet earned a canonical field; core logic must not branch on arbitrary metadata keys.

## Error taxonomy

Adapters translate provider/client errors to shared failures:

- `ConnectorAuthenticationError` — permanent until credentials/configuration change; no automatic retry loop.
- `ConnectorAuthorizationError` — access not permitted; no bypass and no automatic retry loop.
- `ConnectorRateLimitedError` — retry only in accordance with provider limits/Retry-After.
- `ConnectorTimeoutError` — transient and retryable according to operation policy.
- `ConnectorUnavailableError` — temporary provider/server/network failure.
- `ConnectorSchemaError` — provider payload incompatible with adapter expectation; quarantine/report rather than retry indefinitely.
- `ConnectorConfigurationError` — invalid local configuration.

Unknown exceptions are caught at the ingestion boundary and fail only that connector job.

## Rate limiting

Each bookmaker has its own limiter and concurrency semaphore. Limits are configuration derived from the permitted integration contract or provider documentation.

The scheduler must not use a single global limiter that lets one bookmaker consume all capacity.

If a provider returns explicit retry/reset metadata, respect it. Never deliberately rotate identities, proxies, sessions, or other mechanisms to evade a provider limit or access control.

## Retry policy

Retry only transient errors. Baseline recommendation:
- bounded attempts;
- exponential backoff;
- jitter;
- provider Retry-After takes precedence when present;
- total retry duration bounded by the connector job deadline.

Do not retry malformed requests, authentication failures, authorization failures, or deterministic schema mismatches without a code/configuration change.

## Circuit breaker

Maintain breaker state per bookmaker/operation class, not globally. Repeated temporary provider failures may open the breaker for that bookmaker while other bookmakers continue normally.

Health/telemetry must distinguish:
- disabled by configuration;
- healthy;
- degraded;
- throttled;
- circuit open;
- authentication/configuration failure.

## Partial payload failures

Where a feed contains multiple independent events or markets, parsing should be record-isolated when safely possible. A single malformed record should be counted/reported and should not discard valid siblings.

If the payload cannot be trusted structurally, fail the feed rather than manufacturing incomplete canonical data.

## Suspended and missing markets

Suspension is data, not an exception. Map provider suspension/availability states to normalized market/selection availability.

Absence of a market in one fetch must not automatically mean the canonical market was deleted. Provider semantics determine whether disappearance means closure, filtering, stale data, or temporary omission. The application layer owns lifecycle interpretation.

## Source fixtures

Every adapter must include sanitized deterministic fixtures representing:
- normal pre-match event/markets;
- live event when supported;
- suspended market/selection;
- missing optional fields;
- malformed record;
- rate-limit response;
- temporary server failure;
- duplicate/replayed feed data.

Secrets, account identifiers, personal data, or prohibited source material must not be committed.

## Connector contract tests

All adapters must pass shared tests validating:
- stable bookmaker code;
- source IDs are retained;
- odds are valid positive decimal values when available;
- timestamps are timezone-aware;
- missing optional fields do not crash normalization;
- suspended selections are represented explicitly;
- shared error taxonomy is used;
- no provider-specific model escapes the connector package;
- repeated fixture ingestion is deterministic.

## Integration onboarding checklist

Before a new bookmaker connector is accepted:
1. permitted access method documented;
2. credentials/configuration documented without secrets;
3. known rate limits documented;
4. adapter implements common contract;
5. sanitized fixtures committed;
6. shared contract tests pass;
7. timeout/retry/rate-limit behavior covered;
8. source IDs preserved;
9. observability fields emitted;
10. failure of the adapter demonstrably does not interrupt another connector.
