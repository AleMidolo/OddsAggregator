# Software Architect State

Last updated: 2026-09-10

## Current product scope

OddsAggregator is **prematch-only**. Live/in-play matches, markets, odds, ingestion, matching, comparison, arbitrage, alerts, analytics, and QA are out of scope unless the Product Coordinator records an explicit future scope change.

Existing `is_live` / `LIVE` fields remain only as compatibility sentinels for the implemented M1/M2 contracts. Supported prematch flows require `is_live=false`; the M3 matching contract rejects accidental live input.

## Completed architecture foundation

- System/module architecture: `docs/architecture.md`.
- Normalized persistence/data model: `docs/data-model.md`.
- Connector/resilience architecture: `docs/integrations.md`.
- ADR 0001: Python modular monolith + PostgreSQL.
- Shared connector contract: `specs/connector-contract.md`.
- M1/M2 implementation has landed: normalized PostgreSQL persistence, shared connector/runtime primitives, first Bet365/Sportradar prematch connector, production ingestion, and CI.

## Issue #14 — M3 prematch matching architecture

Architecture work defines authoritative rule version `prematch-v1` in `specs/prematch-matching.md` and ADR 0002.

Key decisions:

- `SourceEntityMapping` is always the first lookup; accepted mappings are reused without rescoring or silent remap.
- First-time resolution states are `matched`, `created`, `ambiguous`, `unresolved`, and `rejected`.
- Competition/participant matching uses deterministic normalization, explicit hard filters, scores, auto thresholds, and runner-up margins.
- Event matching requires resolved participant shape, timezone-aware scheduled-time evidence, competition context, and role/position safety; duplicate-risk cases remain ambiguous instead of creating duplicates.
- Default event automatic/guard windows are 30 minutes / 24 hours; canonical tennis uses 6 hours / 48 hours.
- Alias learning occurs only after successful matched/created resolution and never overwrites canonical names.
- Market and selection identity is structural, not fuzzy display-label matching.
- Decimal lines normalize to PostgreSQL `NUMERIC(18,8)` precision with null distinct from zero.
- Shared upstream provider IDs are audit evidence only, never universal canonical IDs.
- Matching decisions are versioned/auditable through `MatchDecision` plus bounded `MatchCandidate` child evidence.
- Replay uses deterministic source fingerprints/decision keys; ambiguous/unresolved/rejected replay does not create duplicate audit rows.
- PostgreSQL structural market/selection uniqueness uses `UNIQUE NULLS NOT DISTINCT` when those M3 layers are implemented.

## Connector contract clarification discovered during #14

Non-null `SourceMarket.market_type`, `SourceMarket.period`, `SourceMarket.scope`, and `SourceSelection.selection_type` used for M3 matching must be shared canonical semantic tokens. Provider display text remains in `name` / `label`; unsupported semantics stay null/unresolved.

The existing Bet365/Sportradar adapter predates this clarification and currently may copy provider market display text into `SourceMarket.market_type`. Generic matching must not compensate with Sportradar-specific rules.

Issue #19 was created for BOOKMAKER INTEGRATION ENGINEER to bring the reference connector into semantic-token conformance.

## Dependency handoff after #14 merges

- #16 — BACKEND / DATA ENGINEER: implement competition/participant/event matching and MatchDecision persistence. Becomes unblocked by #14.
- #19 — BOOKMAKER INTEGRATION ENGINEER: normalize Bet365/Sportradar market/selection semantics. Ready after #14; may run in parallel with #16.
- #15 — BOOKMAKER INTEGRATION ENGINEER: second permitted prematch source. Already ready in parallel and must also conform to the clarified semantic contract.
- #17 — BACKEND / DATA ENGINEER: market/selection matching after #16; real-source acceptance also depends on suitable #15/#19 semantic fixtures.
- #18 — QA / RELEASE ENGINEER: final two-source reconciliation after the preceding implementation path.

## Architecture invariants

- Core/domain/application do not depend on provider-specific payload types.
- Matching remains outside adapters.
- Ambiguous/incomplete semantics are not guessed into canonical identities.
- Historical prematch odds remain append-only/idempotent.
- Network I/O remains outside database transactions.
- Provider failures/rate limits remain independently isolated.
- CI uses sanitized deterministic fixtures and never calls live bookmaker/provider services.
- Only permitted integration methods may be used; never bypass access controls, CAPTCHAs, anti-bot systems, authentication/authorization, rate limits, or geo restrictions.

## Next recommended agent

After issue #14 is merged, BACKEND / DATA ENGINEER should take issue #16. BOOKMAKER INTEGRATION ENGINEER can independently work on #15 and #19.