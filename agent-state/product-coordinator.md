# Product Coordinator State

Last updated: 2026-09-10

## Product scope decision

OddsAggregator is prematch-only. Live/in-play matches, markets, odds, ingestion, matching, comparison, arbitrage, alerts, analytics, and QA are out of scope unless an explicit future product decision changes this constraint.

## Current phase

Milestones M0, M1, and M2 are complete. Milestone M3 — multi-source prematch normalization and matching — is in progress.

## Verified completed foundation

- Normalized domain and PostgreSQL persistence.
- Shared connector DTO/error/resilience/runtime layer.
- CI with Ruff, strict mypy, PostgreSQL/Alembic, and pytest.
- Bet365 reference connector through Sportradar Odds Comparison Prematch v2.
- Connector-to-canonical ingestion with replay idempotency and append-only odds history.
- Bet365 sport-identity correction from issue #11.
- PR #10 merged to `main` as `616a3f72cf760b9636eff6b932ef48ef3898133c`.
- Post-merge CI run #37 succeeded.

## Active M3 issues

- #14 — prematch matching/canonicalization architecture contract — READY, highest priority. It must also align any residual live/in-play architecture assumptions with the prematch-only scope.
- #15 — second permitted prematch source connector — READY in parallel.
- #16 — competition/participant/event prematch matching — BLOCKED by #14.
- #17 — prematch market/selection matching — BLOCKED by #14/#16 and requires #15 fixtures for real-source acceptance.
- #18 — two-source prematch end-to-end QA reconciliation — BLOCKED by #14–#17.

## Coordination decision

SOFTWARE ARCHITECT should take issue #14 next so backend matching code has authoritative normalization, ambiguity, confidence, persistence, and audit semantics that are explicitly prematch-only. BOOKMAKER INTEGRATION ENGINEER may independently proceed with issue #15 using only a documented permitted prematch automated access method.

## Integration constraint

No agent may bypass CAPTCHAs, authentication/authorization controls, anti-bot systems, rate limits, geo-restrictions, or other access controls. Direct Bet365 extraction remains out of scope; the existing reference connector uses the documented Sportradar provider boundary and is prematch-only.
