# Normalized Data Model

## Principles

The canonical model is bookmaker/provider-agnostic. Canonical identities use internal UUIDs; source identifiers are preserved in mapping records for traceability and idempotent ingestion.

OddsAggregator is currently **prematch-only**. Existing `is_live` columns and `LIVE` enum values are compatibility fields inherited from the initial schema; they do not expand product scope. Supported event/snapshot rows must have `is_live = false`, and accidental live/in-play input is rejected before cross-source matching/persistence through the M3 path.

Bookmaker-specific payload fields must not leak into core entities. When provider metadata cannot safely be normalized, keep it in connector DTOs or a deliberately bounded metadata field with documented semantics. Matching must not branch on arbitrary provider metadata.

`specs/prematch-matching.md` defines authoritative matching behavior. ADR 0002 defines matching audit persistence and structural market/selection identity.

## Core entities

### Bookmaker

- `id: UUID`
- `code: str` unique stable internal key
- `name: str`
- `enabled: bool`
- `created_at`, `updated_at`

### Sport

- `id: UUID`
- `code: str` unique canonical key
- `name: str`

Sport matching is outside the M3 matching contract; source sport must already resolve before competition/participant/event matching.

### Competition

- `id: UUID`
- `sport_id: UUID`
- `name: str`
- `country_code: str | null`
- `gender: str | null`
- `season: str | null`

Competition names are not globally unique. Cross-source identity is decided by the matching contract, not a name uniqueness constraint.

### Participant

Represents teams, players, pairs, or other event competitors.

- `id: UUID`
- `sport_id: UUID`
- `type: enum(team, player, pair, other)`
- `name: str`
- `country_code: str | null`

Participant names are not globally unique. Aliases are stored separately so identity history remains explicit.

### Event

- `id: UUID`
- `sport_id: UUID`
- `competition_id: UUID | null`
- `name: str | null`
- `start_time: timestamptz`
- `status: enum(scheduled, suspended, cancelled, postponed, unknown; legacy values may remain for schema compatibility)`
- `is_live: bool` — compatibility sentinel; must be `false` for supported product data
- `created_at`, `updated_at`

Event-participant membership is modeled through `EventParticipant` rather than fixed home/away columns because not every sport is two-sided.

### EventParticipant

- `event_id: UUID`
- `participant_id: UUID`
- `role: str | null` such as `home`, `away`, `player1`, `player2`
- `position: int | null`

Unique constraint on `(event_id, participant_id)` and, where meaningful, `(event_id, role)`.

Roles/positions are identity evidence only when their semantics are normalized. Provider-specific synonyms must be mapped before the matching layer; matching does not guess role meaning from arbitrary labels.

### Market

A canonical logical prematch betting market attached to a canonical event.

- `id: UUID`
- `event_id: UUID`
- `market_type: str` controlled canonical semantic token such as `moneyline`, `spread`, `total`, `both_teams_to_score`
- `period: str` controlled canonical semantic token such as `full_time`, `first_half`, `set_1`
- `line: Decimal | null`
- `scope: str | null`
- `variant: str | null`
- `created_at`, `updated_at`

Market identity is structural, never provider display-label identity:

`(event_id, market_type, period, scope, normalized_line, variant)`

Lines are stored/compared using Decimal semantics normalized to `NUMERIC(18,8)` precision with `ROUND_HALF_EVEN`. Null and numeric zero are distinct.

When market matching is implemented, PostgreSQL must enforce this key with `UNIQUE NULLS NOT DISTINCT` so null scope/line/variant values cannot permit duplicate structural identities.

### Selection

- `id: UUID`
- `market_id: UUID`
- `selection_type: str` controlled canonical role such as `home`, `away`, `draw`, `over`, `under`, `yes`, `no`, `participant`
- `participant_id: UUID | null`
- `line: Decimal | null`
- `name: str | null`

Selection structural identity is:

`(market_id, selection_type, participant_id, normalized_line)`

When selection matching is implemented, PostgreSQL must enforce this key with `UNIQUE NULLS NOT DISTINCT`. Display names do not participate in canonical identity.

### MarketSnapshot

Represents one coherent prematch observation of a bookmaker market.

- `id: UUID`
- `bookmaker_id: UUID`
- `market_id: UUID`
- `run_id: UUID`
- `observed_at: timestamptz`
- `source_updated_at: timestamptz | null`
- `is_live: bool` — compatibility sentinel; must be `false` for supported product observations
- `market_status: enum(open, suspended, closed, unknown)`

### OddsQuote

Append-only historical prematch price/state observation.

- `id: UUID`
- `snapshot_id: UUID`
- `bookmaker_id: UUID`
- `selection_id: UUID`
- `decimal_odds: Decimal | null`
- `is_available: bool`
- `observed_at: timestamptz`
- `source_updated_at: timestamptz | null`
- `observation_key: str`

Use decimal odds as the canonical stored representation. Connector adapters convert source formats before the core sees prices.

`decimal_odds` may be null only for an unavailable selection. `observation_key` is unique and deterministic so replaying the same normalized observation does not duplicate history. Matching/reconciliation never overwrites an earlier quote.

## Source identity and traceability

### SourceEntityMapping

Maps a bookmaker/provider source entity to a canonical entity.

- `id: UUID`
- `bookmaker_id: UUID`
- `entity_type: enum(sport, competition, participant, event, market, selection)`
- `source_id: str`
- `canonical_id: UUID`
- `source_name: str | null`
- `first_seen_at: timestamptz`
- `last_seen_at: timestamptz`
- `connector_version: str | null`

Unique constraint: `(bookmaker_id, entity_type, source_id)`.

This mapping is the first lookup for every previously resolved source entity. Ordinary ingestion never silently moves an existing source mapping to a different canonical UUID.

Equal source IDs from a shared upstream provider are not universal canonical IDs. They may be retained as matching audit evidence only.

### ParticipantAlias

- `participant_id: UUID`
- `normalized_alias: str`
- `source: str | null`

Unique `(participant_id, normalized_alias)`.

### CompetitionAlias

- `competition_id: UUID`
- `normalized_alias: str`
- `source: str | null`

Unique `(competition_id, normalized_alias)`.

Alias insertion is idempotent. Canonical normalized names should be recorded with provenance `canonical`; source aliases are learned only after successful `matched` or `created` resolution. Ambiguous, unresolved, or rejected inputs never teach aliases.

## Ingestion audit entities

### ConnectorRun

- `id: UUID`
- `bookmaker_id: UUID`
- `operation: str`
- `scope: str | null`
- `started_at: timestamptz`
- `finished_at: timestamptz | null`
- `status: enum(running, succeeded, partial, failed, throttled)`
- `attempt_count: int`
- `received_count: int`
- `accepted_count: int`
- `rejected_count: int`
- `error_code: str | null`
- `error_summary: str | null`

Never persist credentials, authentication headers, session tokens, or unsanitized sensitive response bodies in audit records.

## Prematch matching audit entities

Matching uses source-level decisions plus bounded candidate evidence. The earlier standalone `MatchCandidate` sketch is superseded by ADR 0002.

### MatchDecision

One immutable logical decision for a source identity/fingerprint/rule version.

- `id: UUID`
- `bookmaker_id: UUID`
- `entity_type: enum(competition, participant, event, market, selection)`
- `source_id: str`
- `source_fingerprint: char(64)`
- `rule_version: str`
- `decision_key: char(64)` unique
- `state: enum(matched, created, ambiguous, unresolved, rejected)`
- `canonical_id: UUID | null`
- `reason_code: str`
- `best_score: Decimal | null`
- `runner_up_score: Decimal | null`
- `evidence: JSONB`
- `created_at: timestamptz`

`canonical_id` is polymorphic and deliberately has no relational FK; application code validates it against `entity_type`.

`source_fingerprint` contains only normalized identity-bearing input and resolved parent canonical IDs. Price, availability, and transient market state are excluded.

`decision_key = sha256(bookmaker_id | entity_type | source_id | source_fingerprint | rule_version)`.

Replaying identical ambiguous/unresolved/rejected input under the same rule version reuses the same decision row. A changed fingerprint or new rule version may append a new decision. Accepted historical decisions are not rewritten to hide prior outcomes.

Only `matched` and `created` may result in a new `SourceEntityMapping`. `ambiguous`, `unresolved`, and `rejected` must not mutate canonical identity.

Recommended indexes:

- unique `decision_key`;
- `(bookmaker_id, entity_type, source_id, created_at desc)`;
- `(entity_type, state, created_at desc)` for operational review/metrics.

### MatchCandidate

Child evidence belonging to one `MatchDecision`.

- `decision_id: UUID` FK -> `MatchDecision`
- `candidate_id: UUID`
- `rank: int`
- `score: Decimal | null`
- `disposition: enum(eligible, hard_rejected)`
- `reason_codes: JSONB`

Unique `(decision_id, candidate_id)` and `(decision_id, rank)`.

Persist at most the top five eligible candidates for ordinary `matched`/`ambiguous` decisions. Hard-rejected candidate counts/reasons may be summarized in `MatchDecision.evidence` instead of persisting every rejected row. The audit store remains bounded and contains normalized evidence only, never raw provider payloads or secrets.

## Matching identity and replay rules

Matching rule version `prematch-v1` is defined in `specs/prematch-matching.md`.

- Candidate order is deterministic: descending score then ascending canonical UUID string.
- `created` canonical UUIDs use the existing deterministic bookmaker/entity/source UUID factory so retry/concurrency cannot create multiple identities.
- Concurrent uniqueness conflicts are re-read and resolved rather than handled by creating another canonical entity.
- Match decisions are versioned audit history; explicit manual/remediation flows append decisions and deliberately update mappings rather than silently changing ordinary ingestion behavior.

## Indexing baseline

At minimum index:

- source mappings by `(bookmaker_id, entity_type, source_id)`;
- events by `(sport_id, start_time)` and `(competition_id, start_time)`;
- markets by `event_id` plus the structural unique key above when M3 market matching lands;
- selections by `market_id` plus the structural unique key above when M3 selection matching lands;
- snapshots by `(market_id, bookmaker_id, observed_at desc)`;
- quotes by `(selection_id, bookmaker_id, observed_at desc)`;
- connector runs by `(bookmaker_id, started_at desc)`;
- match decisions as specified above.

## Retention

Canonical entities and source mappings are durable. Prematch odds history is append-only and retained by default. Match decisions are durable audit history. Any future archival/partitioning policy must preserve reconstruction of historical market state and matching decisions and must be documented before implementation.