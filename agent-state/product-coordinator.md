# Product Coordinator State

Last updated: 2026-09-10

## Current phase

Milestones M0, M1, and M2 are complete. Milestone M3 — multi-source normalization and matching — is in progress.

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

- #14 — matching/canonicalization architecture contract — READY, highest priority.
- #15 — second permitted source connector — READY in parallel.
- #16 — competition/participant/event matching — BLOCKED by #14.
- #17 — market/selection matching — BLOCKED by #14/#16 and requires #15 fixtures for real-source acceptance.
- #18 — two-source end-to-end QA reconciliation — BLOCKED by #14–#17.

## Coordination decision

SOFTWARE ARCHITECT should take issue #14 next so backend matching code has authoritative normalization, ambiguity, confidence, persistence, and audit semantics. BOOKMAKER INTEGRATION ENGINEER may independently proceed with issue #15 using only a documented permitted automated access method.

## Integration constraint

No agent may bypass CAPTCHAs, authentication/authorization controls, anti-bot systems, rate limits, geo-restrictions, or other access controls. Direct Bet365 extraction remains out of scope; the existing reference connector uses the documented Sportradar provider boundary and is prematch-only.
