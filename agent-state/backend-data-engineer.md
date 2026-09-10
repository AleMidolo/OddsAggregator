# Backend / Data Engineer State

Last updated: 2026-09-10

## Current work
Issue #22 — integrate prematch matching into production connector ingestion.

Implementation branch: `backend/issue-22-ingestion-matching`.

## Implemented
- Two-phase production ingestion: canonical event identity resolves before market fetch/persist.
- Competition, participant, and event identity now routes through `PrematchMatchingService`.
- Mapping-first reuse and immutable same-fingerprint matching decisions remain authoritative.
- Dependency order is sport, competition, participants, then event.
- Non-accepted parent/event outcomes skip dependent markets and increment run rejection counts.
- Successful runs with skipped identities are recorded as `partial` instead of silently succeeded.
- Accidental live input is rejected before parent resolution, preventing prematch parent mappings.
- Optional shared `SourceCompetition` / `SourceParticipant` evidence can accompany event refs.
- Missing competition/participant descriptive evidence is passed through `prematch-v1` as an
  empty semantic name and audited as `rejected / invalid_name` when no mapping already exists.
- Source IDs and hashes are never promoted to semantic matcher names.
- Existing accepted source mappings remain mapping-first even when a later observation omits
  optional descriptive evidence.
- Direct competition/participant/event bootstrap was removed from ingestion persistence.
- Market persistence cannot implicitly create a participant from a selection reference.
- Synthetic PostgreSQL coverage exercises two-source canonical convergence, ambiguity safety,
  missing-evidence rejection, and live rejection.

## Boundaries
- Issue #17 still owns structural market and selection cross-source matching.
- Provider-specific extraction of inline competition/participant evidence stays in connector code.
- Issue #15 supplies the second permitted real source for final M3 validation.
- Issue #19 / connector follow-ups own provider-specific semantic conformance.
- No live/in-play support is introduced.

## Verification
Exact-head repository CI is required for Ruff, strict mypy, Alembic/PostgreSQL, and the full suite.

## Next recommended agent
QA / RELEASE ENGINEER should re-review the issue #22 PR after CI is green. If CI exposes a
backend-owned problem, return to BACKEND / DATA ENGINEER before merge.
