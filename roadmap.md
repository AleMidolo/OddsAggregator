# OddsAggregator Roadmap

This roadmap is dependency-driven. The normalized architecture, connector boundary, persistence semantics, and CI are established; the project is now advancing from one validated source to multi-source canonicalization and matching.

## Milestone M0 — Architecture baseline

**Status: COMPLETE**

Completed deliverables:
- Python modular-monolith architecture and technology baseline;
- normalized domain/persistence semantics;
- bookmaker connector boundary and resilience rules;
- ADR 0001;
- implementation-ready connector contract specification.

## Milestone M1 — Core normalized platform

**Status: COMPLETE**

Completed deliverables:
- normalized domain with no bookmaker-specific dependencies;
- PostgreSQL schema/migrations and source mappings;
- append-only/idempotent historical odds persistence;
- shared connector DTOs and typed errors;
- per-bookmaker timeout, retry, rate-limit, concurrency, and circuit behavior;
- deterministic connector-to-canonical ingestion with network/transaction separation;
- GitHub Actions CI covering Ruff, strict mypy, PostgreSQL/Alembic, and pytest.

Completed issues include #1, #2, #4, and #8.

## Milestone M2 — First permitted reference connector

**Status: COMPLETE**

Completed deliverables:
- Bet365 reference connector through the permitted Sportradar Odds Comparison Prematch v2 boundary;
- documented authentication/entitlement and rate-limit handling;
- sanitized deterministic fixtures and shared connector-contract coverage;
- provider-specific payload isolation;
- source identity correction from issue #11;
- fixture-based Bet365/Sportradar connector -> production ingestion -> canonical PostgreSQL validation;
- green post-merge CI on the production ingestion merge.

Completed issues include #3 and #11. The current reference source is prematch-only and does not imply live Bet365 entitlement.

## Milestone M3 — Multi-source normalization and matching

**Status: IN PROGRESS**

Goal: reconcile equivalent entities across at least two permitted bookmaker/provider sources without relying on bookmaker-specific models or unsafe guessing.

Primary work:
- #14 Architecture: define cross-source matching and canonicalization contract — **READY / highest priority**;
- #15 Bookmaker integration: add a second permitted source — **READY in parallel**;
- #16 Backend: competition, participant, and event matching — **BLOCKED by #14**;
- #17 Backend: canonical market and selection matching — **BLOCKED by #14 and #16**;
- #18 QA: validate two-source reconciliation end to end — **BLOCKED by #14–#17**.

Exit criteria:
- at least two permitted source connectors provide representative overlapping data;
- exact source mappings are reused deterministically;
- competition/participant/event candidates resolve according to explicit evidence and ambiguity rules;
- canonical market/selection matching uses structured semantics rather than display labels;
- ambiguous or unsupported data remains unresolved instead of being guessed;
- replay is idempotent and matching decisions are auditable;
- deterministic two-source CI validates reconciliation, failure isolation, and historical-odds integrity.

## Milestone M4 — Historical odds and comparison

**Status: FUTURE**

Goal: expose reliable current and historical normalized odds across matched sources.

Planned deliverables:
- historical odds query/read model;
- latest-odds retrieval;
- cross-bookmaker odds comparison;
- line-movement foundations;
- freshness/source-quality telemetry.

Entry condition: M3 matching must be sufficiently validated so comparison does not combine unrelated events/markets.

## Milestone M5 — Arbitrage, alerts, and analytics

**Status: FUTURE**

Goal: build downstream product capabilities on validated normalized data.

Planned deliverables:
- arbitrage detection;
- configurable alerts;
- line-movement analysis;
- analytics and monitoring;
- operational APIs/read models as required.

## Sequencing rule

Do not optimize for connector count at the expense of canonical correctness. New integrations must use permitted access methods and shared conformance tests. Matching remains outside adapters, ambiguity must be explicit, and odds comparison/arbitrage work must not precede validated multi-source identity reconciliation.
