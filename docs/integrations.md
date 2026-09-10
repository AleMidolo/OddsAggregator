# Bookmaker Integration Architecture

## Purpose and product scope

Each bookmaker/provider is isolated behind a common adapter contract. The core application must never import or depend on provider-specific response models, URLs, authentication mechanisms, or naming conventions.

OddsAggregator is currently **prematch-only**. Connectors must not add live/in-play endpoints, streaming, polling, fixtures, or product behavior unless the Product Coordinator explicitly changes product scope. Existing `is_live`/`LIVE` connector fields are compatibility sentinels, not a live feature contract.

Only permitted integration methods may be used: official APIs, documented/licensed feeds, or publicly accessible endpoints whose terms allow automated access. Do not bypass CAPTCHAs, authentication/authorization, anti-bot systems, rate limits, geo-restrictions, or other access controls.

## Adapter responsibilities

A provider adapter owns:

- permitted endpoint/feed access;
- legitimate authentication/request signing;
- provider pagination;
- provider-specific throttling headers and limits;
- raw payload validation;
- source identifier extraction;
- conversion of source odds into decimal odds;
- mapping provider statuses into shared connector status values;
- safe translation of provider market/selection concepts into shared canonical semantic tokens when semantics are known;
- retaining enough bounded source metadata for traceability/diagnostics.

An adapter does **not** own:

- canonical event/participant/competition identity;
- cross-source matching;
- canonical market/selection identity selection;
- persistence schema;
- odds comparison or arbitrage detection;
- application-wide scheduling policy.

## Connector interface

The implemented async contract exposes operations equivalent to:

```python
class BookmakerConnector(Protocol):
    bookmaker_code: str

    async def health(self) -> ConnectorHealth: ...
    async def list_sports(self) -> list[SourceSport]: ...
    async def list_events(self, request: EventFeedRequest) -> EventFeedResult: ...
    async def get_markets(self, request: MarketFeedRequest) -> MarketFeedResult: ...
```

Mandatory rules:

1. return shared connector DTOs, never raw provider response classes;
2. network operations are async/cancellable and have explicit timeouts;
3. pagination is contained within or explicitly represented by connector DTOs;
4. errors use the shared typed taxonomy;
5. adapters never write canonical persistence;
6. source IDs and provenance are preserved;
7. supported event data is prematch-only (`is_live=false`);
8. semantic fields used by cross-source matching are shared canonical tokens, not provider display labels.

## Connector DTO semantics

Shared DTOs include `SourceSport`, `SourceCompetition`, `SourceParticipant`, `SourceEvent`, `SourceMarket`, `SourceSelection`, and `SourcePrice`.

DTOs contain normalized primitive types and provider source identifiers. They may retain bounded `metadata` only for source attributes that have not earned a canonical field; core matching logic must not branch on arbitrary metadata keys.

### Prematch event semantics

`SourceEvent.start_time` is timezone-aware. `SourceEvent.is_live` remains physically present for compatibility but must be false for data accepted by current product flows. A connector targeting a documented prematch product should not intentionally return live events. If accidental/provider-misclassified live data reaches the application, the M3 matcher rejects it as out of scope.

### Market and selection semantic fields

`SourceMarket.name` and `SourceSelection.label` are display/source text and are never canonical identity by themselves.

When populated, these fields must carry shared controlled semantics:

- `SourceMarket.market_type`
- `SourceMarket.period`
- `SourceMarket.scope`
- `SourceSelection.selection_type`

Formatting normalization (case/separators) is allowed centrally, but semantic interpretation is adapter-owned because only the adapter understands provider contracts. For example, copying a provider label such as `"1X2 - Full Time"` into `market_type` does **not** make it the canonical `moneyline` token.

If an adapter cannot prove a mapping to the shared semantic registry, it must leave the semantic value null/unsupported and preserve the raw text in `name`/`label` rather than guessing. The matching layer will keep such data unresolved.

Market/selection lines are structured `Decimal` values. Do not scrape or infer a line solely from a display label to satisfy matching.

The authoritative cross-source identity rules and initial market registry are in `specs/prematch-matching.md`.

## Error taxonomy

Adapters translate provider/client errors to shared failures:

- `ConnectorAuthenticationError` — permanent until credentials/configuration change; no automatic retry loop.
- `ConnectorAuthorizationError` — access not permitted; no bypass and no automatic retry loop.
- `ConnectorRateLimitedError` — retry only in accordance with provider limits/Retry-After.
- `ConnectorTimeoutError` — transient and retryable according to operation policy.
- `ConnectorUnavailableError` — temporary provider/server/network failure.
- `ConnectorSchemaError` — payload incompatible with adapter expectation; quarantine/report rather than retry indefinitely.
- `ConnectorConfigurationError` — invalid local configuration.

Unknown exceptions are caught at the ingestion/runtime boundary and fail only that connector job.

## Rate limiting

Each provider/bookmaker has its own limiter and concurrency semaphore. Limits are configured from the permitted integration contract/provider documentation.

The runtime must not use a single global limiter that lets one provider consume all capacity. If a provider returns explicit retry/reset metadata, respect it. Never rotate identities, proxies, sessions, IPs, or credentials to evade limits/access controls.

## Retry policy

Retry transient errors only. Baseline:

- bounded attempts;
- exponential backoff;
- jitter;
- provider Retry-After takes precedence when present;
- total retry duration remains within the connector job deadline.

Do not retry malformed requests, authentication failures, authorization failures, or deterministic schema mismatches without a code/configuration change.

## Circuit breaker

Maintain breaker state per provider/operation class, not globally. Repeated temporary provider failures may open that provider's breaker while unrelated providers continue normally.

Health/telemetry distinguishes disabled, healthy, degraded, throttled, circuit-open, and authentication/configuration failure states.

## Partial payload failures

Where a feed contains multiple independent events/markets, parsing should be record-isolated when safely possible. A malformed sibling should be counted/reported without discarding trusted records.

If the overall payload cannot be trusted structurally, fail the feed rather than manufacture incomplete canonical data.

## Suspended and missing markets

Suspension/unavailability is data, not an exception. Map documented provider suspension/availability states into shared market/selection availability.

Absence of a market in one fetch does not automatically delete a canonical market. Provider semantics determine whether disappearance means closure, filtering, stale data, or temporary omission. The application layer owns lifecycle interpretation.

Availability/status is observational state and must not alter a market/selection's canonical identity key.

## Cross-source matching boundary

The adapter stops after shared DTO normalization. `SourceEntityMapping` lookup, alias evaluation, candidate generation, confidence scoring, ambiguity handling, canonical creation, and match-decision persistence belong to `odds_aggregator.matching` / application services.

Equal source IDs exposed by two bookmaker adapters through the same upstream provider may be recorded as provenance/evidence, but an adapter must not use them to bypass canonical matching.

## Source fixtures

Every adapter must include sanitized deterministic **prematch** fixtures representing, where supported:

- normal prematch events/markets;
- suspended/unavailable market or selection;
- missing optional fields;
- malformed independent record;
- rate-limit response;
- temporary server failure;
- duplicate/replayed feed data.

No live/in-play fixture is required for adapter acceptance. The shared M3 matching suite may use a synthetic `is_live=true` sentinel solely to prove that out-of-scope data is rejected.

Secrets, account identifiers, personal data, or prohibited source material must not be committed.

## Connector contract tests

All adapters must pass shared tests validating:

- stable bookmaker code;
- source IDs retained;
- available odds are valid decimal values;
- timestamps are timezone-aware;
- missing optional fields do not crash normalization;
- suspended/unavailable selections are explicit;
- shared error taxonomy is used;
- provider-specific models do not escape adapter packages;
- repeated fixture parsing is deterministic;
- supported product fixtures are prematch-only;
- populated matching semantic fields conform to the shared controlled-token contract.

## Integration onboarding checklist

Before a connector is accepted:

1. permitted automated **prematch** access method documented;
2. credentials/configuration documented without secrets;
3. known rate limits documented;
4. adapter implements the shared connector contract;
5. shared semantic fields are canonical when populated, otherwise null/unsupported;
6. sanitized deterministic prematch fixtures committed;
7. contract/resilience tests pass;
8. source IDs/provenance preserved;
9. observability fields emitted;
10. failure of the adapter demonstrably does not interrupt another connector.

Cross-source canonical matching remains a separate application concern governed by `specs/prematch-matching.md`.