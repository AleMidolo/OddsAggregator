# Backend / Data Engineer State

Last updated: 2026-09-09

## Current work
Issue #2 — shared connector DTOs and ingestion resilience primitives.

Implementation branch: `backend/issue-2-connector-resilience`.

## Implemented
- Shared Pydantic v2 connector DTOs with preserved source IDs, timezone-aware timestamps, positive decimal odds validation, and explicit availability/suspension states.
- Runtime-checkable `BookmakerConnector` protocol matching `specs/connector-contract.md`.
- Shared typed connector error taxonomy with transient/permanent retry classification.
- Deterministic `FakeBookmakerConnector` for fixture/contract testing.
- Per-bookmaker timeout, overall job deadline, concurrency semaphore, token-bucket rate limiting, bounded exponential retry with jitter, and provider Retry-After handling.
- Per-bookmaker circuit breaker for repeated timeout/unavailable failures.
- Connector operation metrics and isolated run outcomes.
- Failure-isolation helper so one connector failure does not stop unrelated bookmaker operations.
- Implementation documentation in `docs/connector-runtime.md`.

## Verification
- Focused connector/resilience suite: 13 passed.
- Python compileall for new source/tests: passed.
- Long-line check against the repository 100-character Ruff limit: passed.
- Full Ruff, mypy, PostgreSQL, and repository-wide tests are delegated to existing GitHub Actions / QA before merge.

## Coordination note
`README.md`, `roadmap.md`, and `backlog.md` still describe issue #1 as current/issue #2 as blocked even though PR #5 merged issue #1. Those priority documents are owned by PRODUCT COORDINATOR and should be refreshed after this implementation lands.

## Next recommended agent
QA / RELEASE ENGINEER should validate the issue #2 pull request with the existing CI quality and PostgreSQL jobs. After issue #2 is merged, the first permitted reference connector (#3) becomes the next integration dependency.
