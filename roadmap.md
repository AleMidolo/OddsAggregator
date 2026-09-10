# OddsAggregator Roadmap

This roadmap is dependency-driven. **OddsAggregator is a prematch-only platform. Live/in-play matches and live/in-play odds are out of scope for all milestones unless product scope is explicitly changed in the future.**

The normalized architecture, connector boundary, persistence semantics, CI, and event-level prematch matching path are established. The project is now completing market/selection semantics and a second permitted source before end-to-end multi-source acceptance.

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

## Milestone M2 — First permitted prematch reference connector

**Status: COMPLETE**

Completed deliverables:
- Bet365 reference connector through the permitted Sportradar Odds Comparison Prematch v2 boundary;
- documented authentication/entitlement and rate-limit handling;
- sanitized deterministic fixtures and shared connector-contract coverage;
- provider-specific payload isolation;
- source identity correction from issue #11;
- fixture-based Bet365/Sportradar connector -> production ingestion -> canonical PostgreSQL validation.

Completed issues include #3 and #11. No live/in-play extension is planned.

## Milestone M3 — Multi-source prematch normalization and matching

**Status: IN PROGRESS**

Goal: reconcile equivalent prematch entities across at least two permitted bookmaker/provider sources without relying on bookmaker-specific models or unsafe guessing.

Completed M3 foundation:
- #14 Architecture: authoritative `prematch-v1` cross-source matching/canonicalization contract — **COMPLETE**;
- ADR 0002 matching decision/audit persistence — **COMPLETE**;
- #16 Backend: competition, participant, and event matching foundation — **COMPLETE**;
- #22 Backend: integrate prematch matching into production connector ingestion — **COMPLETE**;
- #24 Bookmaker: expose Bet365/Sportradar competition/participant identity evidence — **COMPLETE**.

Remaining work:
- #19 Bookmaker: normalize Bet365/Sportradar prematch market semantics — **READY / highest priority**;
- #15 Bookmaker integration: add a second permitted prematch source — **READY in parallel**;
- #17 Backend: canonical market and selection matching — **READY for synthetic implementation; real-source acceptance depends on #15 and #19**;
- #18 QA: two-source reconciliation end to end — **BLOCKED by #15, #17, and #19**.

Exit criteria:
- at least two permitted prematch sources provide representative overlapping data;
- exact source mappings are reused deterministically;
- competition/participant/event matching follows `prematch-v1` and is integrated into production ingestion;
- both source connectors emit safe structured market/selection semantics;
- canonical market/selection matching uses structured keys rather than provider display labels;
- ambiguous or unsupported data remains unresolved instead of being guessed;
- replay is idempotent and matching decisions are auditable;
- deterministic two-source CI validates reconciliation, failure isolation, and historical-odds integrity.

## Milestone M4 — Prematch historical odds and comparison

**Status: FUTURE**

Goal: expose reliable current and historical prematch odds across matched sources.

Planned deliverables:
- historical prematch odds query/read model;
- latest prematch odds retrieval;
- cross-bookmaker prematch odds comparison;
- prematch line-movement foundations;
- freshness/source-quality telemetry.

Entry condition: M3 matching must be validated so comparison never combines unrelated events, markets, or selections.

## Milestone M5 — Prematch arbitrage, alerts, and analytics

**Status: FUTURE**

Goal: build downstream product capabilities on validated normalized prematch data.

Planned deliverables:
- prematch arbitrage detection;
- configurable alerts;
- prematch line-movement analysis;
- analytics and monitoring;
- operational APIs/read models as required.

## Sequencing rule

Correct canonical semantics take priority over connector count. Resolve known connector conformance gaps before treating source data as matching evidence. New integrations must use permitted prematch access methods and shared conformance tests. Matching remains outside adapters, ambiguity must be explicit, and odds comparison/arbitrage work must not precede validated multi-source identity reconciliation. Live/in-play support is not a roadmap item.
