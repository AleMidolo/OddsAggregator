# OddsAggregator Backlog

Priority is dependency-driven. `READY` means an agent can start without redefining an upstream contract. `BLOCKED` means the listed dependency must land first.

## Active backlog

| Priority | Issue / work item | Suggested Agent | Dependencies | State |
|---|---|---|---|---|
| P0 | #14 Define cross-source matching and canonicalization contract | SOFTWARE ARCHITECT | M1/M2 foundation complete | READY |
| P0 | #15 Add a second permitted source for multi-source validation | BOOKMAKER INTEGRATION ENGINEER | Existing connector contract/runtime | READY (parallel) |
| P0 | #16 Implement competition/participant/event matching foundation | BACKEND / DATA ENGINEER | #14 | BLOCKED |
| P1 | #17 Implement canonical market/selection matching | BACKEND / DATA ENGINEER | #14, #16; #15 fixtures for real-source acceptance | BLOCKED |
| P1 | #18 Validate multi-source reconciliation end to end | QA / RELEASE ENGINEER | #14, #15, #16, #17 | BLOCKED |
| P2 | Historical odds query/read model | BACKEND / DATA ENGINEER | M3 validated matching | BLOCKED |
| P2 | Latest/current odds retrieval and comparison service | BACKEND / DATA ENGINEER | M3 + historical/current query model | BLOCKED |
| P3 | Line-movement analysis foundations | BACKEND / DATA ENGINEER | Historical query model | BLOCKED |
| P3 | Arbitrage detection | BACKEND / DATA ENGINEER | Validated cross-bookmaker comparison | BLOCKED |
| P4 | Alerts and analytics | BACKEND / DATA ENGINEER | Comparison/arbitrage/history foundations | BLOCKED |

## Completed foundation

- #1 normalized domain and PostgreSQL persistence — COMPLETE.
- #2 shared connector DTOs and resilience primitives — COMPLETE.
- #3 first permitted Bet365/Sportradar connector — COMPLETE.
- #4 CI and contract/resilience QA foundation — COMPLETE.
- #8 connector-to-canonical ingestion persistence path — COMPLETE.
- #11 Bet365/Sportradar sport identity correction — COMPLETE.
- First reference connector end-to-end PostgreSQL validation — COMPLETE.
- Post-merge CI run #37 on merge commit `616a3f72cf760b9636eff6b932ef48ef3898133c` — GREEN.

## Current execution order

1. **SOFTWARE ARCHITECT -> #14** to make matching semantics implementation-ready.
2. **BOOKMAKER INTEGRATION ENGINEER -> #15** may proceed in parallel to establish a second permitted source and representative fixtures.
3. **BACKEND / DATA ENGINEER -> #16** after #14.
4. **BACKEND / DATA ENGINEER -> #17** after #16, consuming #15 fixtures for real-source-shaped validation.
5. **QA / RELEASE ENGINEER -> #18** after the full M3 implementation path is available.

## Coordination constraints

- Matching logic belongs outside bookmaker adapters.
- `SourceEntityMapping` remains the deterministic first lookup for previously resolved source entities.
- Do not force ambiguous competitions, participants, events, markets, or selections into canonical identities.
- Market matching must use structured semantics such as market type, period/scope, line, and selection role; provider display labels alone are insufficient.
- New source integrations must document a permitted automated access method before implementation.
- Do not bypass CAPTCHAs, authentication/authorization controls, anti-bot systems, rate limits, geo-restrictions, or other access controls.
- When work is already covered by an active issue, branch, or PR, continue/update it rather than creating a duplicate.
