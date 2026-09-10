# OddsAggregator Backlog

Priority is dependency-driven. `READY` means an agent can start without redefining an upstream contract. `BLOCKED` means the listed dependency must land first.

**Product scope constraint:** all active and future work is prematch-only. Live/in-play matches, markets, odds, ingestion, matching, comparison, arbitrage, alerts, and QA are out of scope unless the product scope is explicitly changed.

## Active backlog

| Priority | Issue / work item | Suggested Agent | Dependencies | State |
|---|---|---|---|---|
| P0 | #19 Normalize Bet365/Sportradar prematch market semantics | BOOKMAKER INTEGRATION ENGINEER | #14 complete; existing reference connector | READY / HIGHEST PRIORITY |
| P0 | #15 Add a second permitted prematch source for multi-source validation | BOOKMAKER INTEGRATION ENGINEER | Existing connector contract/runtime | READY (parallel) |
| P0 | #17 Implement canonical prematch market/selection matching | BACKEND / DATA ENGINEER | #14 and #16 complete; #15/#19 required for real-source acceptance | READY (synthetic) |
| P1 | #18 Validate multi-source prematch reconciliation end to end | QA / RELEASE ENGINEER | #15, #17, #19 | BLOCKED |
| P2 | Historical prematch odds query/read model | BACKEND / DATA ENGINEER | M3 validated matching | BLOCKED |
| P2 | Latest prematch odds retrieval and comparison service | BACKEND / DATA ENGINEER | M3 + historical/current query model | BLOCKED |
| P3 | Prematch line-movement analysis foundations | BACKEND / DATA ENGINEER | Historical query model | BLOCKED |
| P3 | Prematch arbitrage detection | BACKEND / DATA ENGINEER | Validated cross-bookmaker comparison | BLOCKED |
| P4 | Prematch alerts and analytics | BACKEND / DATA ENGINEER | Comparison/arbitrage/history foundations | BLOCKED |

## Completed foundation

- #1 normalized domain and PostgreSQL persistence — COMPLETE.
- #2 shared connector DTOs and resilience primitives — COMPLETE.
- #3 first permitted Bet365/Sportradar prematch connector — COMPLETE.
- #4 CI and contract/resilience QA foundation — COMPLETE.
- #8 connector-to-canonical ingestion persistence path — COMPLETE.
- #11 Bet365/Sportradar sport identity correction — COMPLETE.
- #14 authoritative prematch matching/canonicalization architecture contract — COMPLETE.
- #16 competition/participant/event prematch matching foundation — COMPLETE.
- #22 production `ConnectorIngestionService` integration with `prematch-v1` — COMPLETE.
- #24 Bet365/Sportradar competition/participant identity evidence — COMPLETE.
- PR #23 merged as `6dd50acf2db9cd98650b138c7c341f6fe28fcb91` — COMPLETE.
- Post-merge CI run #74 — GREEN.

## Current execution order

1. **BOOKMAKER INTEGRATION ENGINEER -> #19** to correct the known reference-connector market/selection semantic-token gap before those fixtures are accepted as canonical M3 evidence.
2. **BOOKMAKER INTEGRATION ENGINEER -> #15** may proceed in parallel/next to establish a second permitted prematch source and representative overlapping fixtures.
3. **BACKEND / DATA ENGINEER -> #17** may begin synthetic structural market/selection matching now; real-source acceptance must consume conforming #15 and #19 fixtures.
4. **QA / RELEASE ENGINEER -> #18** only after #15, #17, and #19 are complete.

## Coordination constraints

- Do not implement or plan live/in-play functionality.
- Matching logic belongs outside bookmaker adapters.
- Provider-specific semantic translation belongs inside the corresponding connector; the matcher must not learn provider display-label conventions.
- `SourceEntityMapping` remains the deterministic first lookup for previously resolved source entities.
- Do not force ambiguous competitions, participants, events, markets, or selections into canonical identities.
- Market matching must follow `specs/prematch-matching.md` structured semantics and structural keys; provider display labels alone are insufficient.
- New source integrations must document a permitted automated prematch access method before implementation.
- Do not bypass CAPTCHAs, authentication/authorization controls, anti-bot systems, rate limits, geo-restrictions, or other access controls.
- When work is already covered by an active issue, branch, or PR, continue/update it rather than creating a duplicate.
