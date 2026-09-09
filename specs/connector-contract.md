# Bookmaker Connector Contract Specification

## Scope

This specification is mandatory for every bookmaker adapter.

## Required properties

Every connector:
- has a stable lowercase `bookmaker_code`;
- performs network I/O asynchronously;
- uses only permitted integration methods;
- applies an explicit timeout to each remote operation;
- returns shared connector DTOs rather than provider response objects;
- preserves bookmaker source identifiers on all addressable source entities;
- converts available prices to decimal odds before returning them;
- emits timezone-aware timestamps;
- translates known failures to the shared connector error taxonomy;
- performs no canonical database writes;
- contains no cross-bookmaker matching logic.

## Initial protocol

Implementation may refine names, but the semantic contract is:

```python
from typing import Protocol

class BookmakerConnector(Protocol):
    bookmaker_code: str

    async def health(self) -> ConnectorHealth: ...
    async def list_sports(self) -> list[SourceSport]: ...
    async def list_events(self, request: EventFeedRequest) -> EventFeedResult: ...
    async def get_markets(self, request: MarketFeedRequest) -> MarketFeedResult: ...
```

If a provider naturally returns events and markets together, the adapter may implement that efficiently internally, but it must expose normalized semantics compatible with the application layer.

## DTO requirements

### SourceSport
- `source_id: str`
- `name: str`
- optional stable source code

### SourceCompetition
- `source_id: str`
- `sport_source_id: str`
- `name: str`
- optional country/season metadata

### SourceParticipant
- `source_id: str`
- `name: str`
- participant type when knowable

### SourceEvent
- `source_id: str`
- sport/competition source references
- participant source references with roles/positions where available
- timezone-aware `start_time`
- normalized source status
- `is_live: bool`

### SourceMarket
- `source_id: str`
- `event_source_id: str`
- source market name/type information
- normalized period/scope when adapter can determine it reliably
- line/handicap value where applicable
- availability/suspension state
- selections

### SourceSelection / SourcePrice
- source identifier when provider exposes one
- source label/role
- participant reference where applicable
- decimal odds when available
- availability state
- line where applicable

## Validation

The adapter rejects or marks invalid values that cannot be represented safely. It must not fabricate IDs, prices, participants, or timestamps to satisfy the contract.

Unknown optional source fields may remain absent. Unknown semantic values should use explicit `unknown`/nullable representations rather than guessed canonical values.

## Errors

Shared error categories:
- authentication;
- authorization;
- rate limited;
- timeout;
- temporarily unavailable;
- schema/payload incompatibility;
- local configuration.

The ingestion layer decides retry/circuit behavior from these typed errors.

## Contract-test acceptance criteria

A connector is ready for integration only when shared tests prove:
1. stable connector identity;
2. async/cancellable operations with configured timeout;
3. source IDs survive parsing;
4. timestamps are timezone-aware;
5. odds normalization produces valid decimal values;
6. suspended/unavailable states remain explicit;
7. optional missing fields do not crash parsing;
8. known provider failures map to shared error types;
9. deterministic fixture input yields deterministic DTO output;
10. provider model classes do not escape the connector boundary.
