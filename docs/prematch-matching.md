# Prematch matching runtime

Issue #16 implements the provider-agnostic competition, participant, and event portion of
`specs/prematch-matching.md` rule version `prematch-v1`.

## Boundary

The matcher consumes already-normalized identity inputs and canonical parent IDs. It does not
import bookmaker adapters, call provider services, or interpret provider metadata. Sports must
already be mapped to canonical sports. The `sport_code` supplied for event matching is the
canonical sport code and is used only to select the versioned event time window (`tennis` versus
the default).

`SourceEntityMapping` is always checked first. A mapped source identity returns `reused` without
candidate scoring or another `MatchDecision`. New accepted resolutions (`matched` or `created`)
write the source mapping and first audit decision atomically. Non-accepted outcomes write only
audit state.

## Determinism and safety

- Name, country, season, gender, role, and participant-type normalization follows `prematch-v1`.
- Similarity and score thresholds use deterministic `Decimal` arithmetic with no ML or network
  dependency.
- Candidate ordering is score descending, canonical UUID ascending.
- Created canonical IDs use the same UUIDv5 namespace and identity tuple as the ingestion
  bootstrap, so retries cannot fork a source identity.
- Existing mappings are never silently reassigned.
- Live/in-play events are rejected as `out_of_scope_live` before candidate matching.
- Event role/position reversals and same-participant events inside the guard window but outside
  the automatic window are ambiguity blockers; they do not create duplicate canonical events.
- Equal IDs from a shared upstream provider are not canonical shortcuts.

## Audit persistence

Migration `0003_match_decisions` adds `match_decisions` and bounded child `match_candidates`.
Decision keys are SHA-256 over bookmaker, entity type, source ID, source fingerprint, and rule
version. Replaying the same ambiguous, unresolved, or rejected identity therefore reuses the
same immutable audit decision. Up to five deterministic eligible candidate rows are retained.
Evidence is normalized and bounded; provider payloads and credentials are never stored.

Competition and participant aliases are inserted only after an accepted resolution. Canonical
names are retained, and source names become idempotent aliases with bounded bookmaker
provenance.

## Transaction model

Candidate reads and matching are local database/application work. Each persistence operation
uses a short transaction. No connector or network I/O occurs inside matching transactions.
Concurrent workers rely on deterministic IDs and unique source-mapping/decision keys; a losing
worker re-reads the winning source mapping instead of creating a duplicate canonical identity.

## Deferred work

Issue #17 owns structural market/selection matching and its PostgreSQL `UNIQUE NULLS NOT
DISTINCT` constraints. Issue #15 supplies the second permitted source used by later M3
end-to-end validation. Neither dependency is required for the synthetic issue #16 matcher.
