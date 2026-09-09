# ADR 0001: Modular Monolith with Python and PostgreSQL

- Status: Accepted
- Date: 2026-09-09

## Context

OddsAggregator must ingest data from multiple independent bookmakers, normalize heterogeneous sports/market models, retain historical odds, and later support matching, arbitrage, and analytics.

The codebase is at bootstrap stage. Introducing distributed services before connector contracts, data semantics, and load characteristics are known would add operational complexity without demonstrated benefit.

## Decision

Use a modular monolith implemented in Python 3.12+ with clear internal package boundaries.

Primary technology choices:
- FastAPI for HTTP APIs;
- Pydantic v2 for external/application DTO validation;
- PostgreSQL as authoritative persistence;
- SQLAlchemy 2.x and Alembic for relational persistence/migrations;
- httpx for async bookmaker HTTP integrations;
- Redis only when caching or distributed coordination becomes necessary;
- pytest, Ruff, and mypy for verification/tooling.

Scheduler and ingestion workers may run as separate processes/commands, but they share the same application/domain modules initially.

Bookmaker adapters depend on common connector contracts. The canonical domain must not depend on adapter, HTTP, ORM, or framework types.

## Consequences

### Positive
- Fast initial delivery with one deployable codebase.
- Strong transactionality for canonical mappings and historical odds.
- Easier shared testing of ingestion and matching behavior.
- Clean module boundaries retain a migration path to services when justified.
- Async network I/O supports multiple bookmaker integrations efficiently.

### Negative
- Process-level scaling is coarser than independently deployed microservices.
- Module boundaries require discipline because they are not network-enforced.
- PostgreSQL partitioning/indexing may become necessary as quote history grows.

## Guardrails

Do not split services solely for conceptual cleanliness. A service extraction requires evidence such as independent scaling needs, failure/deployment isolation requirements, ownership boundaries, or operational bottlenecks.

Do not introduce provider-specific structures into canonical domain modules.

Do not use Redis as authoritative odds history.
