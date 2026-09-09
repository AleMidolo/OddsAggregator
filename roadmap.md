# OddsAggregator Roadmap

This roadmap is dependency-driven. The normalized architecture and bookmaker-adapter boundary must remain stable before broad bookmaker integration work begins.

## Milestone M0 — Architecture baseline

**Status: COMPLETE**

Goal: establish the common technical architecture and normalized bookmaker/provider boundary.

Completed deliverables:
- modular-monolith architecture and technology baseline;
- normalized domain and persistence semantics;
- bookmaker connector boundary and resilience rules;
- ADR 0001;
- implementation-ready connector contract specification;
- initial backend, integration, and QA issues (#1–#4).

## Milestone M1 — Core normalized platform

**Status: IN PROGRESS**

Goal: implement the bookmaker-agnostic domain, persistence, connector DTOs, and ingestion resilience foundations.

Primary issues:
- #1 Backend: bootstrap normalized domain and PostgreSQL persistence — **READY / highest priority**;
- #2 Backend: implement shared connector DTOs and ingestion resilience primitives — **BLOCKED until #1 establishes the package skeleton, then READY**;
- #4 QA: establish CI and architecture-level contract/resilience test harness — **READY for CI scaffolding; integration-dependent portions follow #1/#2**.

Exit criteria:
- normalized domain exists with no bookmaker-specific dependencies;
- PostgreSQL migrations create the initial schema;
- source mappings and odds observations are idempotent;
- connector protocol/DTO/error taxonomy are implemented;
- per-bookmaker timeout, retry, rate-limit, concurrency, and circuit behavior exist;
- CI validates lint/type/tests without live bookmaker dependencies.

## Milestone M2 — First permitted reference connector

**Status: BLOCKED by M1**

Goal: validate the architecture end-to-end with one bookmaker/provider that has a permitted automated integration method.

Primary issue:
- #3 Bookmaker integration: add first permitted connector after shared contract lands.

Before implementation, the integration engineer must document the source's permitted access method, authentication requirements, and known rate limits. If permission for automated access cannot be established, that source must not be integrated.

Exit criteria:
- one real connector implements the shared contract;
- provider-specific models remain inside the adapter;
- sanitized fixtures and contract tests exist;
- normalized data can flow through ingestion and persistence;
- one connector failure does not disrupt another connector execution path.

## Milestone M3 — Multi-source normalization and matching

**Status: FUTURE**

Goal: support equivalent entities across at least two permitted sources.

Planned deliverables:
- second permitted connector;
- deterministic source mapping reuse;
- participant, competition, and event candidate matching;
- canonical market/selection matching based on structured semantics;
- confidence and ambiguity handling;
- reconciliation tests and auditability.

## Milestone M4 — Historical odds and comparison

**Status: FUTURE**

Goal: expose reliable current and historical normalized odds across sources.

Planned deliverables:
- historical query services;
- latest-odds retrieval;
- cross-bookmaker odds comparison;
- line-movement foundations;
- freshness/source-quality telemetry.

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

Do not optimize for the number of bookmaker connectors before the normalized core, connector contract, persistence behavior, and CI are validated. Architecture correctness and repeatable connector conformance take priority over integration count.
