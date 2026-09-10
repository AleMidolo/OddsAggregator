# OddsAggregator Architecture

## Status

Architecture baseline for the current **prematch-only** product. Milestones M0-M2 are implemented; Milestone M3 adds cross-source prematch canonicalization and matching.

Live/in-play matches, markets, odds, ingestion, matching, comparison, arbitrage, alerts, analytics, and QA are outside current product scope. Existing `is_live`/`LIVE` compatibility fields do not authorize live functionality and must remain false/unused for supported prematch flows.

## Goals

1. Isolate every bookmaker/provider behind a connector contract.
2. Keep provider-specific payloads out of the core domain while preserving source identifiers and provenance.
3. Ensure one provider failure cannot degrade other connectors.
4. Persist immutable prematch odds history for comparison, line-movement analysis, audit, and future downstream features.
5. Keep cross-source canonicalization and matching outside adapters and independently evolvable.
6. Preserve ambiguity rather than forcing unsafe canonical matches.
7. Start as a modular monolith with independently executable workers.
8. Use only permitted integration methods and respect authentication, access controls, rate limits, anti-bot controls, and geo restrictions.

## Technology baseline

- Python 3.12+
- FastAPI
- Pydantic v2
- PostgreSQL 16
- SQLAlchemy 2.x + Alembic
- httpx with async I/O
- Redis only for caching/distributed coordination when justified
- pytest + pytest-asyncio
- Ruff + strict mypy

PostgreSQL is the source of truth. Redis must never be the only copy of canonical identity, mappings, matching decisions, or odds data.

## Module boundaries

- `odds_aggregator.domain`: canonical entities and domain rules; no HTTP, ORM, framework, or provider dependencies.
- `odds_aggregator.application`: ingestion, normalization, matching orchestration, persistence orchestration, and query use cases.
- `odds_aggregator.connectors`: connector contract and provider-specific adapters.
- `odds_aggregator.persistence`: SQLAlchemy records, repositories, and migrations.
- `odds_aggregator.matching`: competition, participant, event, market, and selection matching rules/services.
- `odds_aggregator.ingestion`: connector execution, retries, rate limiting, concurrency, idempotency, and circuit breaking.
- `odds_aggregator.api`: FastAPI routes and public DTOs.
- `odds_aggregator.observability`: logging, metrics, and tracing hooks.

Dependency direction is inward: connectors, persistence, and API depend on application/domain contracts, never the reverse. Matching must not import provider adapter packages or branch on provider-specific metadata keys.

## Normalized domain

Canonical entities use internal UUIDs. Core entities include:

- Bookmaker
- Sport
- Competition
- Participant
- Event / EventParticipant
- Market
- Selection
- OddsQuote
- MarketSnapshot
- SourceEntityMapping
- ConnectorRun

Provider/source identifiers are stored in dedicated mapping records. Mapping identity is unique on `(bookmaker_id, entity_type, source_id)`.

Every normalized object must remain traceable to its bookmaker/provider, source identifier, retrieval timestamp, and connector version where practical. Equal identifiers emitted by a shared upstream provider are supporting evidence only; they are not universal canonical IDs.

## Connector contract

Each adapter exposes shared connector DTOs rather than raw provider structures. A connector must document its permitted automated access method before acceptance.

A connector owns provider authentication, request/pagination mechanics, payload validation, source identifier extraction, odds conversion, provider status mapping, and safe translation of provider semantics into shared connector fields.

For matching-relevant fields such as `market_type`, `period`, and `selection_type`, a non-null value must be a shared canonical semantic token. Provider display strings belong in `name`/`label`; unknown semantics remain null/unsupported rather than being guessed.

The current connector product boundary is prematch-only.

## Ingestion pipeline

1. Scheduler/runtime selects a due prematch connector/feed scope.
2. Per-provider concurrency and rate-limit guards are acquired.
3. Connector retrieves source data using the documented permitted access method.
4. Adapter validates and maps provider payloads to shared connector DTOs.
5. The application rejects out-of-scope live/in-play inputs.
6. Existing `SourceEntityMapping` is checked first.
7. First-time entities pass through prematch canonicalization/matching as applicable.
8. Persistence atomically records accepted canonical identities/mappings or auditable unresolved decisions.
9. Market snapshots and append-only odds observations are written idempotently.
10. Run outcome and metrics are recorded.

No database transaction may remain open while network I/O is performed.

## Failure isolation and resilience

Each bookmaker/provider has an independent execution policy with:

- timeout budget;
- maximum in-flight requests;
- request rate/burst limits derived from permitted source terms;
- retries for transient failures only;
- exponential backoff with jitter;
- provider `Retry-After` precedence where available;
- circuit-breaker state;
- health telemetry.

Do not retry permanent authentication/authorization failures, malformed requests, deterministic schema incompatibilities, or explicit permanent provider errors.

Malformed independent records should be isolated when safe so one bad record does not discard trusted siblings. Failure of one provider job must not interrupt another provider job.

## Historical prematch odds

Odds history is append-only at quote level. A new `OddsQuote` is persisted when normalized price or relevant selection availability changes, or when an explicitly configured heartbeat policy requires a fresh observation.

`MarketSnapshot` groups quotes observed for one bookmaker market at approximately the same retrieval point. Quotes retain `observed_at` and, when available, `source_updated_at`.

Matching/reconciliation must never rewrite historical odds. Canonical identity corrections use explicit remediation and preserve audit history.

Latest-odds reads should use indexed PostgreSQL queries initially. Caches/materialized read models may be introduced only after M3 identity reconciliation is validated and profiling justifies them.

## Prematch matching

`specs/prematch-matching.md` is the authoritative M3 contract. ADR 0002 records its persistence and structural-identity decisions.

The deterministic resolution order is:

1. exact existing `SourceEntityMapping` reuse;
2. canonical normalization and alias lookup;
3. entity-specific hard filtering/candidate generation;
4. deterministic confidence scoring where applicable;
5. resolution to `matched`, `created`, `ambiguous`, `unresolved`, or `rejected`;
6. auditable decision persistence under matching rule version `prematch-v1`.

### Competitions and participants

Candidate generation is confined to the same canonical sport. Competition matching considers normalized name plus country/season/gender evidence with conflicts acting as hard filters where both sides are known. Participant matching uses normalized name, participant type, and country evidence; conflicting known concrete participant types are rejected.

Aliases are learned only after a successful `matched` or `created` resolution. They never silently replace canonical names and are never learned from ambiguous/rejected data.

### Events

Prematch event matching requires resolved sport and participant identities and, for M3 automatic matching, at least two resolved participants. Candidate evidence includes:

- canonical sport;
- resolved competition context where available;
- timezone-aware scheduled start-time proximity;
- exact participant set/count;
- participant role/position consistency;
- normalized aliases/names as secondary evidence.

Default automatic event time window is 30 minutes with a 24-hour duplicate-risk guard window; canonical sport `tennis` uses 6 hours and 48 hours respectively. Explicit home/away or player1/player2 reversal is a hard conflict. Near duplicate-risk candidates block creation and remain ambiguous instead of creating duplicate canonical events.

Thresholds, scoring weights, normalization rules, and window changes require a new matching rule version.

### Markets and selections

Markets and selections use structural identity rather than fuzzy display-name matching.

Market key:

`(event_id, market_type, period, scope, normalized_line, variant)`

Selection key:

`(market_id, selection_type, participant_id, normalized_line)`

Lines use Decimal semantics quantized to PostgreSQL `NUMERIC(18,8)` precision. Null and numeric zero are distinct. Unsupported/incomplete semantic identity remains unresolved. Structural uniqueness is protected in PostgreSQL using `UNIQUE NULLS NOT DISTINCT` when these layers are implemented.

## Matching audit and idempotency

Existing accepted `SourceEntityMapping` records are authoritative for ordinary replay and bypass rescoring.

First-time matching decisions use a deterministic source fingerprint and `decision_key` scoped by bookmaker, entity type, source ID, fingerprint, and matching rule version. Matching audit state is represented by `MatchDecision` plus bounded candidate details as defined in ADR 0002 and `specs/prematch-matching.md`.

Only `matched` and `created` may result in source mappings. `ambiguous`, `unresolved`, and `rejected` decisions must not mutate canonical identity.

New canonical identities created from a first source continue using deterministic UUID derivation from bookmaker/source identity so retries/concurrent resolution cannot invent duplicates.

## Scheduler and workers

The current modular monolith may run runtime/scheduler/worker concerns as separate commands/processes. Work remains partitionable by bookmaker/provider and feed/sport scope.

Per-provider concurrency prevents one slow source from exhausting the global worker pool. Future distribution must preserve connector and application contracts rather than moving provider semantics into infrastructure.

## API boundary

Initial/future prematch read resources may include:

- `/health/live` (service liveness; **not** live-betting data)
- `/health/ready`
- `/bookmakers`
- `/sports`
- `/competitions`
- `/events`
- `/events/{id}`
- `/events/{id}/markets`
- `/markets/{id}/odds`

Internal ingestion must not depend on the public HTTP API. Public comparison/read API expansion is deferred until M3 matching is validated.

## Observability

Each connector run should expose at minimum: `run_id`, bookmaker/provider, operation, attempt, latency, records received/accepted/rejected, rate-limit wait, retry count, and terminal status.

Matching metrics should include counts/rates of reused, matched, created, ambiguous, unresolved, and rejected resolutions by entity type and matching rule version, without leaking sensitive provider data.

Never log credentials, authentication headers, session tokens, or unsanitized sensitive payloads.

## Testing architecture

Required layers:

1. domain and normalization unit tests;
2. shared connector contract tests;
3. adapter tests with sanitized deterministic fixtures/mocked HTTP;
4. PostgreSQL persistence/migration tests;
5. resilience/failure-isolation tests;
6. deterministic matching positive/negative/ambiguous/replay tests from `specs/prematch-matching.md`;
7. two-source end-to-end prematch reconciliation tests before M3 completion.

CI must not depend on live bookmaker/provider services. Live/in-play product tests are out of scope; the only live sentinel required by the matching specification verifies rejection of accidental out-of-scope input.

## Evolution rule

Do not split into microservices until measurable scaling, deployment isolation, or ownership constraints justify it. Do not advance odds comparison/arbitrage/read-model work ahead of validated M3 multi-source identity reconciliation. Product scope remains prematch-only unless explicitly changed by the Product Coordinator.