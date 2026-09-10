# ADR 0002: Prematch matching decisions and structural identity

- Status: Accepted
- Date: 2026-09-10
- Scope: Milestone M3 prematch cross-source matching

## Context

OddsAggregator now has a normalized PostgreSQL model, source mappings, connector DTOs, a production ingestion path, and one permitted prematch reference connector. Milestone M3 requires equivalent entities from multiple sources to converge on canonical identities without unsafe guessing.

The initial data-model sketch proposed a single `MatchCandidate` row with a candidate score and pending/accepted/rejected status. That shape cannot represent source-level resolution states, deterministic replay, matching-rule versioning, runner-up ambiguity, unresolved/rejected outcomes, or bounded evidence. The existing canonical market and selection tables also have no database uniqueness constraint for their structured identity keys.

The product is prematch-only. Existing domain/connector/database `is_live` and `LIVE` compatibility fields predate that product decision.

## Decision

### 1. Matching remains outside connectors

Cross-source matching is owned by the matching/application layer. Bookmaker adapters may normalize provider semantics into shared connector fields, but they must not select canonical entities or contain cross-bookmaker rules.

`SourceEntityMapping(bookmaker_id, entity_type, source_id)` remains the deterministic first lookup. Existing mappings are reused without rescoring and are never silently remapped by ordinary ingestion.

### 2. Persist source-level MatchDecision audit records

Introduce a `match_decisions` persistence concept with, at minimum:

- bookmaker/source/entity identity;
- deterministic source fingerprint;
- matching `rule_version`;
- unique deterministic `decision_key`;
- state: `matched`, `created`, `ambiguous`, `unresolved`, or `rejected`;
- selected canonical UUID when applicable;
- reason code;
- best and runner-up scores when applicable;
- bounded normalized JSON evidence;
- creation timestamp.

The canonical UUID is deliberately polymorphic and is validated by application/entity type rather than a relational foreign key.

Matching decisions are audit history. Replaying the same unresolved input under the same rule version reuses the deterministic decision. A later changed input/rule version or explicit remediation may append another decision; history is not rewritten to pretend an earlier result was different.

### 3. MatchCandidate becomes child evidence

`match_candidates` belongs to one `MatchDecision` and stores bounded candidate detail: candidate UUID, deterministic rank, score, disposition, and reason codes. Persist at most the top five eligible candidates for ordinary matching decisions; aggregate hard-rejection counts/reasons in decision evidence when that is sufficient.

This replaces the earlier standalone `MatchCandidate` sketch.

### 4. Alias learning is post-resolution evidence

Participant and competition aliases are learned only from successfully `matched` or `created` source identities. Aliases never overwrite canonical names and are never learned from ambiguous, unresolved, or rejected inputs.

### 5. Market and selection identity is structural

Canonical market identity is:

`(event_id, market_type, period, scope, normalized_line, variant)`

Canonical selection identity is:

`(market_id, selection_type, participant_id, normalized_line)`

PostgreSQL 16 `UNIQUE NULLS NOT DISTINCT` constraints/indexes must protect these structural keys so null identity components cannot create duplicate canonical rows.

Lines are `Decimal` values normalized to the persistence precision (`NUMERIC(18,8)`) and are never parsed from provider display labels by the matcher.

### 6. Shared connector semantic fields are controlled when non-null

When `SourceMarket.market_type`, `SourceMarket.period`, or `SourceSelection.selection_type` is populated for cross-source matching, it must express a shared canonical semantic token, not a provider display string. Raw provider labels remain in `SourceMarket.name` / `SourceSelection.label` or bounded connector metadata.

If an adapter cannot safely map a provider concept into a shared semantic token, the semantic field remains null/unsupported and matching returns an unresolved result rather than guessing from a label.

This is a clarification of the connector boundary, not permission for the matching layer to import provider rules.

### 7. Shared upstream IDs are evidence only

Equal source IDs issued by a common upstream provider may be stored as supporting audit evidence but are not universal canonical IDs and do not bypass normal matching requirements.

### 8. Existing live-capable fields are compatibility sentinels

No migration removes existing `is_live` columns or `LIVE` enum values during M3 because they are already part of implemented persistence/DTO contracts and removing them would create unrelated migration churn.

For the current product scope:

- supported ingestion/matching is prematch-only;
- `is_live` must be false for supported observations;
- live/in-play inputs are rejected at the application/matching boundary and do not create cross-source mappings through this path;
- no live connector, matching algorithm, fixture requirement, or downstream feature may be added without an explicit future product-scope decision.

## Consequences

- Issue #16 must implement the decision/audit persistence required for competition, participant, and event matching.
- Issue #17 must add structural uniqueness protection as it implements canonical market/selection matching.
- Existing adapters must conform to the clarified semantic-field contract before their market data is used for cross-source matching.
- Matching behavior is versioned; changes to normalization, thresholds, weights, time windows, line precision, or semantic-key construction require a new rule version plus regression fixtures.
- Ambiguous data remains unresolved rather than being forced into a canonical identity.
- Existing live-capable fields may remain physically present but do not expand product scope.

## Alternatives considered

### Reuse only SourceEntityMapping

Rejected. It records accepted mappings but cannot explain why a first-time candidate was ambiguous, unresolved, or rejected, and cannot safely support rule-version replay/audit.

### Keep the original standalone MatchCandidate sketch

Rejected. It lacks a source-level decision, deterministic replay key, rule version, runner-up margin, structured reasons, and a bounded evidence model.

### Use provider market names as canonical market identity

Rejected. Display labels vary by provider and locale and are not a safe cross-source semantic contract.

### Treat equal upstream provider IDs as universal canonical IDs

Rejected. Namespace/stability guarantees are source-specific and cannot be assumed across bookmaker connectors without a separate architectural decision.

### Remove all live-capable fields now

Deferred. The product is prematch-only, but removing already-implemented compatibility fields would enlarge the M3 migration surface without improving matching correctness.