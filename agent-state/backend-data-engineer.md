# Backend / Data Engineer State

Last updated: 2026-09-09

## Current work
Issue #8 — connector-to-canonical ingestion persistence path.

Implementation branch: `backend/issue-8-ingestion-persistence`.

## Implemented
- Bookmaker-agnostic `ConnectorIngestionService` consuming the shared connector protocol.
- Explicit network/persistence boundary so connector I/O never runs inside DB transactions.
- SQLAlchemy ingestion store with mapping-first deterministic first-source identity bootstrap.
- Canonical sport, competition, participant, event, market, selection, snapshot, and quote writes.
- Deterministic replay handling for source mappings, snapshots, and historical quote observations.
- Nullable odds persistence for explicit suspended/unavailable selections without fabricated prices.
- Connector run audit lifecycle and counters.
- Unit tests for transaction/network separation and unavailable observation semantics.
- PostgreSQL integration coverage for replay idempotency and append-only price changes.
- Implementation documentation in `docs/ingestion.md`.

## Verification
Repository CI is required for Ruff, strict mypy, Alembic/PostgreSQL, and the full suite.

## Next recommended agent
QA / RELEASE ENGINEER should validate the issue #8 PR and complete the final issue #4
reference/fake connector -> production ingestion -> PostgreSQL smoke acceptance path after merge.
