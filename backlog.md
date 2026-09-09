# OddsAggregator Backlog

Priority is dependency-driven. `READY` means an agent can start without redefining an upstream contract. `BLOCKED` means the listed dependency must land first.

| Priority | Issue / work item | Suggested Agent | Dependencies | State |
|---|---|---|---|---|
| P0 | #1 Bootstrap normalized domain and PostgreSQL persistence | BACKEND / DATA ENGINEER | Architecture baseline | READY |
| P0 | #4 Establish CI and contract/resilience test harness | QA / RELEASE ENGINEER | None for CI scaffolding; #1/#2 for implementation-dependent tests | READY (partial) |
| P0 | #2 Implement shared connector DTOs and ingestion resilience primitives | BACKEND / DATA ENGINEER | #1 package skeleton | BLOCKED |
| P1 | #3 Add first permitted bookmaker/provider connector | BOOKMAKER INTEGRATION ENGINEER | #2 shared connector implementation + documented permitted access method | BLOCKED |
| P1 | Validate reference connector end-to-end through persistence | QA / RELEASE ENGINEER | #1, #2, #3 | BLOCKED |
| P2 | Add second permitted source connector | BOOKMAKER INTEGRATION ENGINEER | Reference connector validated | BLOCKED |
| P2 | Implement participant/competition/event matching foundations | BACKEND / DATA ENGINEER | Stable normalized data + representative multi-source fixtures | BLOCKED |
| P2 | Implement market/selection matching | BACKEND / DATA ENGINEER | Event matching + canonical market semantics | BLOCKED |
| P3 | Implement historical odds query/read model | BACKEND / DATA ENGINEER | Stable append-only ingestion | BLOCKED |
| P3 | Implement cross-bookmaker odds comparison | BACKEND / DATA ENGINEER | Multi-source matching + current odds queries | BLOCKED |
| P4 | Implement arbitrage detection | BACKEND / DATA ENGINEER | Odds comparison | BLOCKED |
| P4 | Implement alerts, line-movement analysis, and analytics | BACKEND / DATA ENGINEER | Historical/comparison foundations | BLOCKED |

## Current execution order

1. **BACKEND / DATA ENGINEER → issue #1**.
2. After #1 creates the package/project skeleton, continue with **BACKEND / DATA ENGINEER → issue #2**.
3. **QA / RELEASE ENGINEER → issue #4** may scaffold CI in parallel, but must consume rather than invent shared production contracts.
4. Only after #2 is implemented should **BOOKMAKER INTEGRATION ENGINEER → issue #3** implement a real connector, and only after confirming a permitted automated access method.

## Coordination constraints

- Do not start broad bookmaker integration before connector contracts and conformance tests are stable.
- Do not embed event/market matching logic inside bookmaker adapters.
- Do not add bookmaker-specific DTO dependencies to core/domain/application layers.
- Do not create work that bypasses CAPTCHAs, authentication/authorization, anti-bot controls, rate limits, geo-restrictions, or other access controls.
- When a task is already covered by an active issue, branch, or PR, update/continue that work rather than creating a duplicate.
