# Normalized Data Model

## Principles

The canonical model is bookmaker-agnostic. Canonical identities use internal UUIDs; bookmaker identifiers are preserved in source-mapping records for traceability and idempotent ingestion.

Bookmaker-specific payload fields must not leak into core entities. When provider metadata cannot yet be normalized, keep it in connector-layer DTOs or a deliberately bounded metadata field with documented semantics.

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

### Competition
- `id: UUID`
- `sport_id: UUID`
- `name: str`
- `country_code: str | null`
- `gender: str | null`
- `season: str | null`

### Participant
Represents teams, players, pairs, or other event competitors.

- `id: UUID`
- `sport_id: UUID`
- `type: enum(team, player, pair, other)`
- `name: str`
- `country_code: str | null`

Aliases should be stored separately so matching history remains explicit.

### Event
- `id: UUID`
- `sport_id: UUID`
- `competition_id: UUID | null`
- `name: str | null`
- `start_time: timestamptz`
- `status: enum(scheduled, live, suspended, finished, cancelled, postponed, unknown)`
- `is_live: bool`
- `created_at`, `updated_at`

Event-participant membership is modeled through `EventParticipant` rather than fixed home/away columns because not every sport is two-sided.

### EventParticipant
- `event_id: UUID`
- `participant_id: UUID`
- `role: str | null` such as `home`, `away`, `player1`, `player2`
- `position: int | null`

Unique constraint on `(event_id, participant_id)` and, where meaningful, `(event_id, role)`.

### Market
A canonical logical betting market attached to an event.

- `id: UUID`
- `event_id: UUID`
- `market_type: str` canonical controlled value such as `moneyline`, `spread`, `total`, `both_teams_to_score`
- `period: str` such as `full_time`, `first_half`, `set_1`
- `line: Decimal | null`
- `scope: str | null`
- `variant: str | null`
- `created_at`, `updated_at`

Market identity is based on structured semantics, not provider display labels.

### Selection
- `id: UUID`
- `market_id: UUID`
- `selection_type: str` canonical role such as `home`, `away`, `draw`, `over`, `under`, `yes`, `no`, `participant`
- `participant_id: UUID | null`
- `line: Decimal | null`
- `name: str | null`

### MarketSnapshot
Represents one coherent observation of a bookmaker market.

- `id: UUID`
- `bookmaker_id: UUID`
- `market_id: UUID`
- `run_id: UUID`
- `observed_at: timestamptz`
- `source_updated_at: timestamptz | null`
- `is_live: bool`
- `market_status: enum(open, suspended, closed, unknown)`

### OddsQuote
Append-only historical price/state observation.

- `id: UUID`
- `snapshot_id: UUID`
- `bookmaker_id: UUID`
- `selection_id: UUID`
- `decimal_odds: Decimal`
- `is_available: bool`
- `observed_at: timestamptz`
- `source_updated_at: timestamptz | null`
- `observation_key: str`

Use decimal odds as the canonical stored representation. Connector adapters convert source formats before the core sees prices.

`observation_key` is unique and deterministic for a normalized observation so replaying the same feed does not duplicate history.

## Source identity and traceability

### SourceEntityMapping
Maps a bookmaker identifier to a canonical entity.

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

The mapping table is the first matching lookup for all previously resolved source entities.

### ParticipantAlias
- `participant_id: UUID`
- `normalized_alias: str`
- `source: str | null`

### CompetitionAlias
- `competition_id: UUID`
- `normalized_alias: str`
- `source: str | null`

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

## Matching support

Unresolved or low-confidence source entities must not be silently attached to arbitrary canonical records.

### MatchCandidate
Recommended initial representation for reviewable matching decisions:

- `id: UUID`
- `bookmaker_id: UUID`
- `entity_type: str`
- `source_id: str`
- `candidate_id: UUID`
- `score: Decimal`
- `status: enum(pending, accepted, rejected)`
- `created_at`, `resolved_at`

This may be introduced after the initial deterministic mapping path if implementation scope needs to remain smaller.

## Indexing baseline

At minimum index:
- source mappings by `(bookmaker_id, entity_type, source_id)`;
- events by `(sport_id, start_time)` and `(competition_id, start_time)`;
- markets by `event_id`;
- snapshots by `(market_id, bookmaker_id, observed_at desc)`;
- quotes by `(selection_id, bookmaker_id, observed_at desc)`;
- connector runs by `(bookmaker_id, started_at desc)`.

## Retention

Canonical entities and source mappings are durable. Odds history is append-only and retained by default. Any future archival/partitioning policy must preserve the ability to reconstruct historical market state and must be documented before implementation.
