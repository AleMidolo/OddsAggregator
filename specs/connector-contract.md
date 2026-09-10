# Bookmaker Connector Contract Specification

## Scope

This specification is mandatory for every bookmaker/provider adapter.

The current OddsAggregator product is **prematch-only**. Live/in-play endpoints, feeds, matching, and odds are outside scope unless the Product Coordinator records an explicit future scope change. Existing shared DTO fields such as `SourceEvent.is_live` and the `LIVE` status value are compatibility fields and do not authorize live functionality.

Cross-source matching is defined separately in `specs/prematch-matching.md`.

## Required properties

Every connector:

- has a stable lowercase `bookmaker_code`;
- performs network I/O asynchronously;
- uses only a documented permitted integration method;
- applies an explicit timeout to every remote operation;
- returns shared connector DTOs rather than provider response objects;
- preserves provider source identifiers on all addressable source entities;
- converts available prices to decimal odds before returning them;
- emits timezone-aware timestamps;
- translates known failures to the shared connector error taxonomy;
- performs no canonical database writes;
- contains no cross-bookmaker matching logic;
- returns only prematch product data through supported current flows;
- uses canonical shared semantic tokens for matching-relevant fields when those fields are populated.

## Protocol

```python
from typing import Protocol

class BookmakerConnector(Protocol):
    bookmaker_code: str

    async def health(self) -> ConnectorHealth: ...
    async def list_sports(self) -> list[SourceSport]: ...
    async def list_events(self, request: EventFeedRequest) -> EventFeedResult: ...
    async def get_markets(self, request: MarketFeedRequest) -> MarketFeedResult: ...
```

If a provider naturally returns events and markets together, the adapter may optimize its own internal access path, but it must expose shared DTO semantics compatible with the application layer.

## DTO requirements

### SourceSport

- `source_id: str`
- `name: str`
- optional stable source sport code

Do not populate `code` with a broad provider classification that is not a unique/reliable sport code.

### SourceCompetition

- `source_id: str`
- `sport_source_id: str`
- `name: str`
- optional country/season metadata

### SourceParticipant

- `source_id: str`
- `name: str`
- participant type when safely knowable

### SourceEvent

- `source_id: str`
- sport/competition source references
- participant source references with normalized roles/positions when known
- timezone-aware `start_time`
- normalized source status
- `is_live: bool` compatibility sentinel

For supported product data, `is_live` must be false and the normalized status must not be `live`. An adapter targeting a documented prematch feed should not intentionally return live events. If accidental live input reaches the application, the prematch matching boundary rejects it.

### SourceMarket

- `source_id: str`
- `event_source_id: str`
- `name: str | null` for source/display text
- `market_type: str | null` shared canonical semantic token
- `period: str | null` shared canonical semantic token
- `scope: str | null` shared canonical semantic token when applicable
- structured Decimal `line`/handicap when applicable
- availability/suspension state
- selections

`market_type`, `period`, and `scope` are **not** generic copies of provider display text. If the adapter cannot safely translate the provider contract into a supported shared semantic token, leave the semantic field null/unsupported and retain source text in `name` or bounded metadata.

The initial matching registry and structural identity rules are defined in `specs/prematch-matching.md`.

### SourceSelection

- source identifier when the provider exposes one
- `label` for source/display text
- `selection_type: str | null` shared canonical semantic token
- participant source reference where applicable
- structured Decimal line where applicable
- price/availability state

`selection_type` must not be populated with arbitrary provider display labels. Unknown/unsupported semantics remain null so the matcher can preserve an unresolved state rather than guess.

### SourcePrice

- valid decimal odds when available;
- explicit availability state;
- optional timezone-aware source update timestamp.

Unavailable selections must not carry fabricated odds.

## Semantic-token ownership

Provider semantic translation belongs to the adapter because it requires knowledge of the documented provider contract. The shared matcher may normalize only formatting of already-canonical tokens (for example casing/separators); it must not infer provider meaning from free-form labels or arbitrary metadata.

Examples of canonical market types supported by the M3 matching contract include `moneyline`, `spread`, `total`, and `both_teams_to_score`. A provider-specific string such as `"Match Winner"` belongs in `SourceMarket.name` unless the adapter has an explicit, tested mapping proving it is the canonical `moneyline` concept for the corresponding period/scope.

Market/selection lines are Decimal values. Do not parse a line from a display label merely to satisfy canonical matching.

## Validation

The adapter rejects or omits values that cannot be represented safely. It must not fabricate IDs, prices, participants, timestamps, semantic types, or lines to satisfy the contract.

Unknown optional source fields may remain absent. Unknown semantic values use explicit unknown/null representations rather than guessed canonical values.

## Errors

Shared error categories:

- authentication;
- authorization;
- rate limited;
- timeout;
- temporarily unavailable;
- schema/payload incompatibility;
- local configuration.

The ingestion/runtime layer decides retry/circuit behavior from these typed errors. Authentication, authorization, deterministic schema, and configuration failures are non-transient.

## Permitted integration requirement

Before a connector implementation is accepted, repository documentation must record its permitted automated prematch access method, authentication/entitlement expectations, and known rate-limit behavior.

No connector may bypass CAPTCHA, authentication/authorization, anti-bot controls, published/enforced rate limits, geo restrictions, or other source controls.

## Contract-test acceptance criteria

A connector is ready for integration only when shared tests prove:

1. stable connector identity;
2. async/cancellable operations with configured timeout;
3. source IDs survive parsing;
4. timestamps are timezone-aware;
5. available odds normalize to valid decimal values;
6. suspended/unavailable state remains explicit;
7. missing optional fields do not crash parsing;
8. known provider failures map to shared error types;
9. deterministic fixture input yields deterministic DTO output;
10. provider model classes do not escape the connector boundary;
11. supported fixture/event output is prematch-only;
12. non-null market/selection semantic fields are explicit shared canonical tokens backed by tested provider mappings rather than raw display labels.

CI uses sanitized fixtures/mocks and never depends on a live bookmaker/provider service.