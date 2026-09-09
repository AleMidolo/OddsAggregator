# Connector-to-canonical ingestion

Issue #8 introduces the production application seam between shared connector DTOs and
PostgreSQL persistence.

## Execution boundary

`ConnectorIngestionService` owns connector orchestration. It resolves the configured
bookmaker, fetches sports/events/markets asynchronously, and only then calls the
synchronous `IngestionStore`. `SQLAlchemyIngestionStore` owns a fresh short transaction
for each run-state update, sport write, or event/market persistence batch. A database
transaction is therefore never held open across connector network I/O.

The bookmaker row must already exist and be enabled under the connector's stable
`bookmaker_code`.

## First-source identity bootstrap

Persistence always checks `SourceEntityMapping` first. If no mapping exists for a
first-source entity, an internal UUID is derived deterministically from bookmaker,
entity type, and exact source ID. Replays therefore resolve the same canonical entity
without cross-bookmaker heuristics.

The current connector event contract carries participant and competition source IDs but
not always their descriptive metadata. In that case the exact source ID is retained as
a temporary source-derived label because the canonical schema requires a non-null name.
No semantic name is guessed. A future authoritative DTO can replace that display label
without changing the source mapping.

Selections without a provider source ID receive a deterministic internal identity from
their structured market/selection semantics. No source ID or source mapping is
fabricated. Missing market type/period values are stored explicitly as `unknown`.

## Historical observations

Each market observation creates/reuses a deterministic `MarketSnapshot`. Selection
quotes are append-only and use a deterministic observation key. When a provider
`source_updated_at` timestamp is available, it is the replay identity timestamp, so
retrieving the same provider observation later does not create duplicate history. If no
source timestamp exists, the retrieval timestamp identifies the observation.

Unavailable selections are persisted as `is_available = false` with
`decimal_odds = NULL`. Migration `0002_nullable_unavailable_odds` makes that state
representable without inventing a price. Available quotes still require decimal odds
greater than 1.

## Testing

Backend tests use deterministic fake connector DTOs only. PostgreSQL integration tests
verify mapping reuse, replay idempotency, append-only changed prices, null prices for
unavailable selections, and connector-run audit records. CI never calls a live provider.
