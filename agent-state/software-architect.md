# Software Architect State

Last updated: 2026-09-09

## Completed
- Established system architecture in `docs/architecture.md`.
- Defined normalized entities and persistence semantics in `docs/data-model.md`.
- Defined bookmaker adapter, resilience, rate-limit, and testing rules in `docs/integrations.md`.
- Accepted ADR 0001: Python modular monolith + PostgreSQL.
- Added mandatory connector contract in `specs/connector-contract.md`.
- Created implementation issues #1 through #4.

## Architecture constraints
- Core/domain cannot depend on bookmaker-specific types.
- Every bookmaker is isolated behind a connector adapter.
- Canonical entities use internal UUIDs; source IDs are preserved in mappings.
- Historical odds are append-only and ingestion must be idempotent.
- Matching is separate from connectors.
- Per-bookmaker timeout, retry, rate limiting, and circuit state prevent one provider from breaking others.
- CI uses sanitized fixtures/mocks rather than live bookmaker services.
- Only permitted integration methods may be used; never bypass access controls, CAPTCHAs, anti-bot systems, authentication, rate limits, or geo restrictions.

## Ready work
- Issue #1: Backend domain + PostgreSQL persistence — ready now.
- Issue #4: QA/CI scaffolding — ready now; implementation-dependent tests can follow #1/#2.
- Issue #2: Shared connector DTO/resilience primitives — proceed after or alongside project skeleton from #1 without duplicating package bootstrap.
- Issue #3: First bookmaker connector — blocked on #2 and on documenting a permitted source access method.

## Next recommended agent
BACKEND / DATA ENGINEER should take issue #1.
