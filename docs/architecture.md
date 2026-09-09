# OddsAggregator Architecture

## Status
Initial architecture baseline for the first production increment.

## Goals
1. Isolate every bookmaker behind a connector contract.
2. Keep bookmaker-specific payloads out of the core domain while preserving source identifiers for traceability.
3. Ensure one bookmaker failure cannot degrade other connectors.
4. Persist immutable odds history for comparison, arbitrage, line-movement analysis, and audit.
5. Keep event and market matching outside adapters and independently evolvable.
6. Start as a modular monolith with independently executable workers.
7. Use only permitted integration methods and respect source authentication, access controls, rate limits, anti-bot controls, and geo restrictions.

## Technology baseline
- Python 3.12+
- FastAPI
- Pydantic v2
- PostgreSQL
- SQLAlchemy 2.x + Alembic
- httpx with async I/O
- Redis only for caching/distributed coordination when justified
- pytest + pytest-asyncio
- Ruff + mypy

PostgreSQL is the source of truth. Redis must never be the only copy of odds or mapping data.

## Module boundaries
Suggested packages:
- `odds_aggregator.domain`: canonical entities and domain rules; no HTTP, ORM, framework, or bookmaker dependencies.
- `odds_aggregator.application`: ingestion, normalization, matching, persistence orchestration, and query use cases.
- `odds_aggregator.connectors`: connector contract and bookmaker-specific adapters.
- `odds_aggregator.persistence`: SQLAlchemy models, repositories, and migrations.
- `odds_aggregator.matching`: event, participant, competition, market, and selection matching.
- `odds_aggregator.ingestion`: scheduling, connector execution, retries, rate limiting, idempotency, and circuit breaking.
- `odds_aggregator.api`: FastAPI routes and public DTOs.
- `odds_aggregator.observability`: logging, metrics, and tracing hooks.

Dependency direction is inward: adapters, persistence, and API depend on application/domain, never the reverse.

## Normalized domain
Canonical entities use internal UUIDs. Initial entities:
- Bookmaker
- Sport
- Competition
- Participant
- Event
- Market
- Selection
- OddsQuote
- MarketSnapshot

Bookmaker/source identifiers are stored in dedicated mapping records. Mapping identity is unique on `(bookmaker_id, entity_type, source_id)`.

Every normalized object must remain traceable to its bookmaker, source identifier, retrieval timestamp, and connector version where practical.

## Connector contract
Each bookmaker adapter exposes normalized connector DTOs rather than raw provider structures to the core. A connector must document its permitted access method.

A connector execution is scoped to one bookmaker and feed/sport scope where practical. Connector-specific authentication, payload parsing, pagination, provider rate-limit metadata, and source IDs remain inside the adapter.

## Ingestion pipeline
1. Scheduler selects a due connector/feed scope.
2. Per-bookmaker concurrency and rate-limit guards are acquired.
3. Connector retrieves source data using permitted access methods.
4. Adapter validates and maps provider payloads to connector DTOs.
5. Normalization converts DTOs to canonical candidates while retaining source mappings.
6. Matching resolves canonical sport, competition, participant, event, market, and selection identities.
7. Persistence performs idempotent identity upserts and append-only odds writes.
8. Run outcome and metrics are recorded.

No database transaction may remain open while performing network I/O.

## Failure isolation and resilience
Each bookmaker has an independent execution policy with:
- timeout budget;
- maximum in-flight requests;
- request rate/burst limits derived from permitted source terms;
- retries for transient failures only;
- exponential backoff with jitter;
- circuit-breaker state;
- health telemetry.

Do not retry permanent authentication/authorization failures, malformed requests, schema violations requiring code changes, or explicit permanent provider errors.

Malformed records should be isolated when possible so one bad event does not discard an otherwise valid feed.

## Historical odds
Odds history is append-only at quote level. A new `OddsQuote` is persisted when normalized price or relevant selection state changes, or when a configured heartbeat requires a fresh observation.

`MarketSnapshot` groups selection quotes observed for one bookmaker market at approximately the same retrieval point. Quotes retain `observed_at` and, when available, `source_updated_at`.

Latest-odds queries should use indexed PostgreSQL queries initially. Introduce caches/materialized latest tables only after profiling.

## Matching
Matching is a separate service and must never be embedded in bookmaker adapters.

Initial event matching pipeline:
1. exact existing source mapping;
2. reliable normalized external key, when available;
3. deterministic candidate filtering by sport, competition, start-time window, and participant shape;
4. normalized names and aliases;
5. confidence scoring;
6. automatic match only above a configured threshold; otherwise preserve as unmatched/reviewable.

Market matching uses canonical market type, period/scope, line or handicap parameters, and selection role. Display strings alone are insufficient.

## Idempotency
Every connector execution receives a `run_id`.

Identity writes rely on database uniqueness constraints. Odds observations require a deterministic observation key or equivalent uniqueness constraint so replayed normalized observations do not duplicate history.

Transactions are bounded to logical batches.

## Scheduler and workers
Phase 1 may run scheduler and workers as separate processes/commands within one deployment. The application must expose a scheduler/queue abstraction so distribution can be added later without changing connector or domain contracts.

Jobs are partitioned by bookmaker and optionally by feed/sport scope. Per-bookmaker concurrency prevents one slow provider from exhausting the global worker pool.

## API boundary
Initial read/operational resources:
- `/health/live`
- `/health/ready`
- `/bookmakers`
- `/sports`
- `/competitions`
- `/events`
- `/events/{id}`
- `/events/{id}/markets`
- `/markets/{id}/odds`

Internal ingestion must not depend on the public HTTP API.

## Observability
Each connector run should expose at minimum: `run_id`, bookmaker, operation, attempt, latency, records received/accepted/rejected, rate-limit wait, retry count, and terminal status.

Metrics should include connector success/failure rate, fetch latency, normalization failures, unmatched entities, quote throughput, retry counts, throttling, and age of latest successful update per bookmaker.

Never log credentials, authentication headers, session tokens, or unsanitized sensitive payloads.

## Testing architecture
Required layers:
1. domain unit tests;
2. shared connector contract tests;
3. adapter tests with sanitized fixtures and mocked HTTP;
4. PostgreSQL persistence integration tests;
5. resilience tests for timeout, retries, rate limiting, malformed records, duplicate delivery, partial failures, and historical integrity;
6. end-to-end smoke test from fixture connector through normalized persistence.

CI must not depend on live bookmaker services.

## Evolution rule
Do not split into microservices until measurable scaling, deployment isolation, or ownership constraints justify it. Current module boundaries should be preserved so they can become service boundaries later if needed.
