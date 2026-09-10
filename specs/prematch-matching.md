# Prematch Cross-Source Matching and Canonicalization Contract

Status: authoritative for Milestone M3

Rule version: `prematch-v1`

## 1. Scope and invariants

This specification defines bookmaker-agnostic matching for **prematch-only** competition, participant, event, market, and selection identities.

Live/in-play data is outside the current product scope. A source event with `is_live=true` or normalized status `live` must not enter cross-source matching or create canonical/mapping records through this path. It is rejected with reason `out_of_scope_live`. Existing `is_live` fields are compatibility sentinels and must remain `false` for supported prematch observations.

The matcher is an application/domain service. It must not import bookmaker adapter packages or branch on provider-specific metadata. Provider/source IDs are provenance, never canonical IDs.

`SourceEntityMapping(bookmaker_id, entity_type, source_id)` is always the first lookup. If a valid mapping exists, its canonical identity is reused without fuzzy rescoring. Automatic remapping of an existing source identity is forbidden; corrections require an explicit remediation/manual decision outside ordinary ingestion.

Sport matching is not redefined here. M3 assumes the source sport has already resolved to a canonical `Sport` before competition/participant/event matching begins.

## 2. Resolution states

A first-time source identity resolves to exactly one of these states:

- `matched`: an existing canonical identity was selected automatically.
- `created`: no plausible existing identity exists and a new canonical identity was created.
- `ambiguous`: one or more plausible candidates exist but automatic-match requirements are not satisfied.
- `unresolved`: required parent identity or structured semantic evidence is missing, so candidate resolution cannot safely run.
- `rejected`: the input is invalid, outside product scope, or violates a hard matching invariant.

`reused` is the logical result when `SourceEntityMapping` already exists; it is not a new matching decision and must not create repeated audit rows.

Only `matched` and `created` create a new `SourceEntityMapping`. `ambiguous`, `unresolved`, and `rejected` never attach the source entity to a canonical identity.

Candidate ordering is deterministic: descending score, then ascending canonical UUID string. A tie therefore has zero score margin and cannot auto-match.

## 3. Text normalization

### 3.1 Strict normalized name

`normalize_name(value)` must:

1. trim leading/trailing whitespace;
2. apply Unicode NFKC normalization;
3. apply Unicode `casefold()`;
4. replace punctuation, symbol, and separator runs with a single ASCII space;
5. collapse repeated whitespace to one space;
6. preserve letters and digits;
7. return no semantic substitutions.

The matcher must **not** automatically remove club suffixes (`fc`, `cf`, `ac`), expand abbreviations, translate words, infer nicknames, or delete age/gender qualifiers. Those transformations can collapse distinct entities and belong in explicit aliases when validated.

An empty normalized competition or participant name is invalid.

### 3.2 Accent-folded form

For similarity only, compute a folded form by applying Unicode NFKD to the strict normalized name and removing combining marks. The strict form remains the alias-storage form.

### 3.3 Deterministic name similarity

For a source name against each canonical name and stored alias:

- strict exact equality: `1.00`;
- folded exact equality when strict strings differ: `0.98`;
- otherwise compute both:
  - normalized Levenshtein similarity: `1 - distance / max(len(a), len(b))`;
  - token Dice similarity: `2 * |A intersect B| / (|A| + |B|)` over token sets;
- use the maximum of those two fuzzy values, capped at `0.97`.

The entity `name_score` is the maximum score against its canonical name and all aliases.

No randomization, ML model, external LLM, locale-dependent transliteration, or network service is allowed in M3 matching.

## 4. Metadata normalization

### Country

Country codes are trimmed and upper-cased only when they are valid two-letter codes supplied by normalized source data. Missing/invalid values become unknown. The matcher never infers country from an entity name.

### Season

Trim whitespace and normalize `/`, Unicode dashes, and hyphens to `-`.

- `YYYY-YYYY` remains that form.
- `YYYY-YY` expands the second year in the closest non-decreasing century, e.g. `2026-27 -> 2026-2027` and `1999-00 -> 1999-2000`.
- A single `YYYY` remains `YYYY`.
- Other non-empty season labels are compared only by normalized exact equality; they are not fuzzily interpreted.

### Gender

When available as normalized canonical/source metadata, gender is compared by a controlled normalized token. The matcher never infers gender from display names. The current `SourceCompetition` contract does not require gender; absence is neutral evidence.

### Roles and positions

Event and selection roles are formatting-normalized to lowercase snake-case tokens only. Provider-specific role synonyms must be mapped by the adapter when semantics are known; the matcher must not infer `host -> home`, for example, from arbitrary labels.

## 5. Shared scoring semantics

All scores are Decimal values in `[0, 1]` and are rounded to five decimal places only for persistence/display; threshold comparisons use the unrounded deterministic value.

For optional metadata components:

- known and equal: `1.0`;
- unknown on either side: `0.5`;
- known conflict: entity-specific handling below.

A candidate must satisfy both the total auto threshold and all entity-specific auto gates. Let `margin = best_score - runner_up_score`; if there is only one candidate, `runner_up_score = 0`.

## 6. Competition matching

### Preconditions and hard filters

- Canonical sport identity must already be resolved.
- Candidate competitions are restricted to the same canonical sport.
- If both country codes are known and differ, reject that candidate.
- If both normalized seasons are known and differ, reject that candidate.
- If both normalized genders are known and differ, reject that candidate.

### Score

`competition_score = 0.70*name + 0.15*country + 0.10*season + 0.05*gender`

### Decision thresholds

- auto-match: score `>= 0.92`, name score `>= 0.90`, and margin `>= 0.08`;
- plausible candidate: score `>= 0.75`;
- if at least one plausible candidate exists but auto-match fails: `ambiguous`;
- if no plausible candidate exists: `created`.

A same-name competition in a conflicting country/season is a valid distinct identity and does not block `created`.

## 7. Participant matching

### Preconditions and hard filters

- Canonical sport identity must already be resolved.
- Candidates are restricted to the same canonical sport.
- When both participant types are known and neither side is the generic `other` value, conflicting types reject that candidate.
- Country conflict is not a hard rejection because provider semantics may represent team country, nationality, or affiliation differently; it contributes zero to the country component.

### Score

`participant_score = 0.80*name + 0.15*type + 0.05*country`

For `type`, missing or `other` on either side contributes `0.5` unless both known concrete values agree (`1.0`).

### Decision thresholds

- auto-match: score `>= 0.92`, name score `>= 0.94`, and margin `>= 0.08`;
- plausible candidate: score `>= 0.78`;
- if at least one plausible candidate exists but auto-match fails: `ambiguous`;
- if no plausible candidate exists: `created`.

## 8. Alias lifecycle

`CompetitionAlias` and `ParticipantAlias` are evidence, not alternate canonical identities.

- The normalized canonical name should exist as an alias with provenance `canonical`.
- A source normalized name may be learned as an alias **only after** that source identity reaches `matched` or `created`.
- Never learn aliases from `ambiguous`, `unresolved`, or `rejected` decisions.
- Adding an alias never overwrites `Competition.name` or `Participant.name`.
- Alias insertion is idempotent under the existing `(canonical_id, normalized_alias)` uniqueness rule.
- Use bounded provenance such as `bookmaker:<bookmaker_code>`; the corresponding `SourceEntityMapping.source_name` retains source-specific traceability.

Alias evidence may help subsequent source identities, but it cannot retroactively remap an already-resolved `SourceEntityMapping`.

## 9. Prematch event matching

### Preconditions

- Source sport must resolve to a canonical sport.
- Every source participant reference used for event identity must resolve to a canonical participant first.
- M3 automatic event resolution requires at least two resolved participants. Inputs with insufficient participant shape are `unresolved` with reason `insufficient_participant_evidence` unless an exact source mapping already exists.
- If the source competition reference exists, it should be resolved before event scoring. An unresolved required competition yields `unresolved:parent_unresolved` rather than guessed context.

### Time windows

All timestamps are timezone-aware and compared as UTC instants.

Configuration defaults for rule version `prematch-v1`:

- default automatic event window: `30 minutes`;
- default conflict/guard window: `24 hours`;
- canonical sport code `tennis`: automatic window `6 hours`, guard window `48 hours`.

Future sport-specific overrides require configuration plus fixture coverage; changing defaults requires a new matching rule version.

### Candidate generation

Generate event candidates within the guard window and same canonical sport. For each candidate:

- if both competition IDs are known and differ, the candidate is hard-rejected;
- participant count and canonical participant set must match exactly for an eligible candidate;
- when comparable role maps are present on both sides, role-to-participant assignments must agree;
- otherwise, when comparable position maps are present on both sides, position-to-participant assignments must agree;
- an explicit role/position reversal is a hard conflict, never a positive match;
- eligible candidates must fall within the automatic event window.

A candidate with the exact participant set inside the guard window but outside the automatic window, or with an explicit role/position conflict, is a **duplicate-risk blocker**. If no other candidate auto-matches, do not create a new canonical event; return `ambiguous` with a specific conflict reason.

### Event score

For eligible candidates:

- participant-shape score: `1.0` (eligibility already requires exact set/count);
- role score: `1.0` when comparable role/position maps agree, `0.5` when either side lacks comparable role/position data;
- time score: `1 - 0.5*(absolute_delta / automatic_window)`; therefore it decreases from `1.0` to `0.5` across the allowed window;
- competition score: `1.0` when both resolved competitions agree, `0.5` when one side has no competition;
- name score: normalized name similarity when both event names exist, otherwise `0.5`.

`event_score = 0.50*participant_shape + 0.10*role + 0.25*time + 0.10*competition + 0.05*name`

### Event decision thresholds

- auto-match: score `>= 0.90` and margin `>= 0.05`;
- plausible eligible candidate: score `>= 0.78`;
- plausible candidate(s) without auto-match: `ambiguous`;
- duplicate-risk blocker with no auto-match: `ambiguous`;
- no plausible candidate and no duplicate-risk blocker: `created`.

## 10. Canonical market semantics

Market matching is deterministic structural matching, not fuzzy name matching.

### Canonical semantic tokens

`market_type`, `period`, `scope`, `variant`, and `selection_type` are semantic tokens. Format them with Unicode NFKC, casefolding, trim, and snake-case separator normalization. This normalization changes formatting only; it must not infer provider meaning.

A non-null `SourceMarket.market_type` or `SourceSelection.selection_type` used for cross-source matching must already represent a controlled canonical semantic token. Provider display text belongs in `name`/`label`. If an adapter cannot map a provider market/outcome safely, it must return the semantic field as `null`/unsupported rather than copy an arbitrary display label into a canonical semantic field.

The initial controlled market registry contains at least:

- `moneyline` — period required, market line must be null;
- `spread` — period required, signed handicap semantics required;
- `total` — period required, total line required;
- `both_teams_to_score` — period required, market line must be null.

Additional market families require explicit registry/tests; unknown market semantics remain unresolved and are never matched by label similarity.

### Decimal line normalization

Lines/handicaps must be parsed as `Decimal`, never binary float, and quantized to eight fractional digits using `ROUND_HALF_EVEN`, matching PostgreSQL `NUMERIC(18,8)`. Null and numeric zero are distinct. A line must never be guessed from a display label.

For canonical `spread`, `Market.line` is the signed handicap from the canonical home/player1 side perspective. If a provider exposes per-selection handicaps, the semantic adapter/normalizer may derive this only when structured participant roles make the sign unambiguous and the opposing line is consistent. Otherwise the market is unresolved.

For canonical `total`, the effective threshold is the normalized market line; if the same threshold is repeated on selections it must agree.

### Market identity key

Within an already-resolved canonical event:

`MarketKey = (event_id, market_type, period, scope, normalized_line, variant)`

Null values remain null and are identity-bearing; the matcher does not silently default missing scope/variant/period values. `market_type` and `period` are mandatory for automatic matching.

- exactly one canonical row with the same key: `matched`, score `1.0`;
- no row and all required semantics are supported/complete: `created`;
- unsupported or incomplete identity semantics: `unresolved`;
- more than one canonical row with the same key: `rejected:data_integrity_duplicate_key` and operational alert.

A different period, scope, variant, or normalized line is a different market, not a fuzzy candidate.

## 11. Selection identity

Selection matching is structural and occurs only inside an already-resolved canonical market.

`SelectionKey = (market_id, selection_type, canonical_participant_id, effective_line)`

Rules:

- display `label`/`name` is never sole identity evidence;
- participant-linked types (`home`, `away`, `player1`, `player2`, `participant`) require a resolved participant when the market semantics identify a competitor;
- if a source omits participant ID for `home`/`away`/`player1`/`player2`, the matcher may derive it only from a unique canonical event role of the same structured type;
- `draw`, `yes`, and `no` normally have no participant reference;
- `over`/`under` use the normalized total threshold; when selection line is absent, the canonical market line may supply the effective line; when both are present they must agree;
- null and numeric zero are distinct;
- unsupported/unknown `selection_type` is `unresolved` rather than label-matched.

Within one market, exactly one matching structural key yields `matched`; none yields `created` when semantics are complete; duplicate canonical keys are a data-integrity rejection.

## 12. Shared upstream provider identifiers

Two bookmaker adapters may expose IDs issued by the same upstream data provider. Equality of those IDs may be recorded as audit evidence (`shared_provider_id_equal=true`) but, in `prematch-v1`, contributes **no score** and never bypasses sport/competition/participant/time/role/market semantic rules.

An upstream ID must not become a universal canonical ID without a separate ADR proving namespace ownership and stability.

## 13. Idempotency and replay

- Existing source mapping always wins and bypasses rescoring.
- `created` canonical IDs must use the existing deterministic canonical-ID factory based on bookmaker/source identity so transaction retry cannot create multiple canonical rows.
- A first-time decision has an identity fingerprint containing only normalized identity-bearing fields and resolved parent canonical IDs; odds, availability, and transient market status are excluded.
- `decision_key = sha256(bookmaker_id | entity_type | source_id | source_fingerprint | rule_version)`.
- Replaying the same unresolved/ambiguous/rejected input under the same rule version upserts/reuses the same decision record rather than duplicating audit rows.
- A changed unresolved identity fingerprint or new rule version may produce a new immutable decision record.
- Once a source mapping is accepted, later ordinary ingestion never automatically moves it to another canonical ID.

## 14. Matching audit persistence

The previous single `MatchCandidate` sketch is insufficient because it cannot represent a source-level resolution, rule version, deterministic replay key, runner-up margin, or reasons for unresolved/rejected outcomes. ADR 0002 therefore introduces `MatchDecision` plus candidate detail rows.

### MatchDecision

Required logical fields:

- `id: UUID`
- `bookmaker_id: UUID`
- `entity_type: competition | participant | event | market | selection`
- `source_id: str`
- `source_fingerprint: char(64)`
- `rule_version: str`
- `decision_key: char(64)` unique
- `state: matched | created | ambiguous | unresolved | rejected`
- `canonical_id: UUID | null`
- `reason_code: str`
- `best_score: Decimal | null`
- `runner_up_score: Decimal | null`
- `evidence: JSONB`
- `created_at: timestamptz`

`canonical_id` is intentionally polymorphic and is not a database foreign key. Application code validates its entity type.

Evidence is bounded, normalized, and non-secret; it may contain component scores, parent canonical IDs, time delta/window, normalized source name, candidate counts, and shared-upstream-ID equality. Never persist credentials, auth headers, tokens, or raw provider payloads.

### MatchCandidate

Persist the top five eligible candidates, ordered deterministically, for `matched` and `ambiguous` decisions and whenever candidate detail helps explain `unresolved`.

Required logical fields:

- `decision_id: UUID`
- `candidate_id: UUID`
- `rank: int`
- `score: Decimal | null`
- `disposition: eligible | hard_rejected`
- `reason_codes: JSONB`

Unique `(decision_id, candidate_id)` and `(decision_id, rank)`.

Hard-rejection summary counts/reasons may be stored in `MatchDecision.evidence` instead of persisting every rejected candidate. The audit store must remain bounded.

Matching decisions are audit history. They are not rewritten to fabricate a different historical outcome; a later explicit/manual remediation appends a new decision and updates the source mapping through a dedicated path.

## 15. Canonical uniqueness constraints

Issue #16/#17 implementations must add database protection appropriate to each implemented layer.

For PostgreSQL 16, market and selection structural identities should use `UNIQUE NULLS NOT DISTINCT` constraints/indexes so null identity components do not permit duplicate canonical keys:

- market: `(event_id, market_type, period, scope, line, variant)`;
- selection: `(market_id, selection_type, participant_id, line)`.

Competition/participant names are **not** globally unique.

## 16. Transaction boundary

Network I/O remains outside database transactions. Matching/canonical persistence for one logical source entity should execute in a bounded transaction that atomically records the accepted canonical identity/source mapping and its first decision when practical.

Ambiguous/unresolved/rejected decision persistence must not mutate canonical entities or create source mappings.

Concurrent workers resolving the same source identity rely on source-mapping/decision uniqueness and deterministic canonical IDs; uniqueness conflicts are re-read and resolved, never handled by creating a second canonical identity.

## 17. Required deterministic fixtures

Backend and QA tests must include at least these prematch cases:

1. competition punctuation/casing variation with matching sport/country/season -> automatic match;
2. same competition display name but conflicting country or season -> distinct identity, not auto-match;
3. participant alias (for example validated alias vs canonical name) with matching sport/type -> automatic match;
4. two plausible same-sport participant candidates with insufficient differentiating evidence -> ambiguous;
5. equivalent event with exact canonical participant set/roles and a small timezone-normalized schedule difference -> automatic match;
6. same participant set with explicit home/away or player1/player2 reversal -> no auto-match and no duplicate canonical creation;
7. same participant set with event time just outside the automatic window but inside guard window -> ambiguous duplicate-risk state;
8. distinct event outside the guard window -> new canonical identity;
9. replay of matched, created, ambiguous, unresolved, and rejected inputs -> no duplicate mappings/decisions;
10. market labels differ but canonical market type/period/scope/line/variant agree -> structural match;
11. same market type with different period or line -> distinct canonical markets;
12. total line `2.5` vs `2.50000000` -> same normalized line; a materially different decimal line remains distinct;
13. selection display labels differ but structured type/participant/effective line agree -> structural match;
14. unsupported/null market or selection semantics -> unresolved rather than guessed;
15. equal source IDs from a shared upstream provider across two bookmaker connectors -> audit evidence only, not identity shortcut;
16. any `is_live=true` or status `live` event -> `rejected:out_of_scope_live`, with no canonical mapping from this path.

Fixtures remain sanitized and deterministic. CI never calls a live bookmaker/provider service.

## 18. Versioning

Any change to normalization, scoring weights, thresholds, event windows, line precision, or semantic-key construction changes matching behavior and therefore requires a new rule version plus deterministic regression fixtures. Pure implementation refactors that preserve outputs may keep `prematch-v1`.
