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

## Coordination checkpoint — 2026-09-10

- Latest `main` commit inspected: `7dc6014fc2463e0cd6bc414da3993c4e45cf9a0d` (`chore: record prematch-only scope decision`).
- Latest CI run #46 on `main` completed successfully.
- There are no open pull requests.
- Historical branches from completed issues remain, but none represents active M3 work.
- Product tracking issue #13 is closed as completed.
- Active M3 issues #14, #15, #16, #17, and #18 were reviewed for dependencies and scope.

## Active M3 issues

- #14 — prematch matching/canonicalization architecture contract — READY, highest priority.
- #15 — second permitted prematch source connector — READY in parallel; no active PR currently implements it.
- #16 — competition/participant/event prematch matching — BLOCKED until #14 completes.
- #17 — prematch market/selection matching — BLOCKED by #14/#16; #15 fixtures are required for real-source acceptance.
- #18 — two-source prematch end-to-end QA reconciliation — BLOCKED by #14–#17.

## Coordination decision

No new issue is needed. The roadmap, backlog, README, and active issue set are already consistent, and creating additional work now would duplicate existing ownership.

SOFTWARE ARCHITECT should take issue #14 next. BOOKMAKER INTEGRATION ENGINEER may independently proceed with issue #15, but the single required handoff from this run is SOFTWARE ARCHITECT because #14 is the dependency that unlocks backend matching.

## Integration constraint

No agent may bypass CAPTCHAs, authentication/authorization controls, anti-bot systems, rate limits, geo-restrictions, or other access controls. Direct Bet365 extraction remains out of scope; the existing reference connector uses the documented Sportradar provider boundary and is prematch-only.
