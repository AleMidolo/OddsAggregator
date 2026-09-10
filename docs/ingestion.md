# Connector-to-canonical ingestion

The production ingestion seam consumes shared connector DTOs, resolves prematch canonical
identity, and persists accepted markets and historical odds into PostgreSQL.

## Execution boundary

`ConnectorIngestionService` owns asynchronous connector orchestration. It fetches sports and
events, then calls the synchronous `IngestionStore` to resolve canonical event identity before
fetching markets. Only accepted event identities proceed to `get_markets` and market persistence.

All persistence and matching store calls own short local database transactions. No database
transaction is held open across connector network I/O.

The bookmaker row must already exist and be enabled under the connector's stable
`bookmaker_code`.

## Prematch identity resolution

Sports retain the original mapping-first bootstrap behavior. A stable canonical sport code may
allow a second source sport ID to reuse an existing canonical sport.

Competition, participant, and event identities are resolved through `PrematchMatchingService`
under `prematch-v1` in dependency order:

1. canonical sport mapping;
2. competition when present;
3. event participants;
4. event.

Existing `SourceEntityMapping` rows are reused before scoring. For unseen identities, matching
uses the existing deterministic candidate/scoring and immutable `MatchDecision` rules. Accepted
`matched` and `created` resolutions produce canonical mappings. `ambiguous`, `unresolved`, and
`rejected` outcomes remain unmapped and stop the dependent event path.

An event rejected or deferred during identity resolution does not trigger a market request and
cannot attach markets, selections, snapshots, or odds to a guessed canonical event. The
connector run records the skipped event in `rejected_count` and completes as `partial` when the
rest of the run succeeds.

Accidental live input is rejected at the event matcher before competition or participant
resolution, so a live sentinel cannot create prematch parent mappings as a side effect.

## Identity evidence from event-first connectors

The shared event DTO remains backward compatible with source-reference-only connectors.
`SourceEvent` may optionally embed its matching-relevant `SourceCompetition`, and each
`SourceEventParticipant` may optionally embed its `SourceParticipant`. These are shared DTOs,
not provider payload objects.

When embedded identity evidence is present, ingestion uses its name and supported metadata for
cross-source matching. When descriptive identity evidence is absent, ingestion derives a
stable opaque hash label from the exact source ID and still resolves through the matcher. This
preserves deterministic first-source creation while preventing provider IDs with common prefixes
from becoming accidental fuzzy-name evidence. The original source ID remains preserved in
`SourceEntityMapping`.

Cross-source connectors should provide the shared identity evidence when their documented feed
already exposes it; provider-specific extraction remains inside the connector package. The
backend does not inspect arbitrary connector metadata to infer names or identity semantics.

## Market and selection boundary

Issue #22 resolves identity only through the canonical event level. Market and selection writes
continue to reuse exact source mappings or deterministic source identities until issue #17 adds
structural cross-source market/selection matching.

Selection participant references may reuse participants already resolved for the event or an
existing participant source mapping. Market persistence no longer creates participant identities
implicitly.

Selections without a provider source ID still receive a deterministic internal identity from
their structured source semantics. No source ID or source mapping is fabricated.

## Historical observations

Each accepted market observation creates or reuses a deterministic `MarketSnapshot`. Selection
quotes remain append-only and use a deterministic observation key. When a provider
`source_updated_at` timestamp is available, it is the replay identity timestamp, so retrieving
the same provider observation later does not create duplicate history. If no source timestamp
exists, the retrieval timestamp identifies the observation.

Unavailable selections are persisted as `is_available = false` with `decimal_odds = NULL`.
Available quotes still require decimal odds greater than 1.

## Testing

CI uses deterministic fake connectors only. PostgreSQL integration coverage includes:

- first-source replay and append-only changed-price behavior;
- two source IDs converging onto one competition, participant set, and event;
- mapping-first replay with immutable matching decisions;
- ambiguous parent resolution producing no event/market write and no market network call;
- connector-run partial/rejected accounting;
- live-sentinel rejection before parent identity resolution;
- unavailable observations without fabricated prices.

CI never calls a live bookmaker or provider service.
