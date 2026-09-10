# Product Coordinator State

Last updated: 2026-09-10

## Product scope decision

OddsAggregator is prematch-only. Live/in-play matches, markets, odds, ingestion, matching, comparison, arbitrage, alerts, analytics, and QA are out of scope unless an explicit future product decision changes this constraint.

## Current phase

Milestones M0, M1, and M2 are complete. Milestone M3 — multi-source prematch normalization and matching — is in progress.

## Verified completed M3 foundation

- Issue #14 / PR #20: authoritative `prematch-v1` matching/canonicalization contract and ADR 0002 — complete.
- Issue #16 / PR #21: competition, participant, and event prematch matching foundation — complete.
- Issue #22 / PR #23: production `ConnectorIngestionService` integration with `prematch-v1` — complete.
- Issue #24: Bet365/Sportradar structured competition/participant identity evidence — complete.
- PR #23 merged to `main` as `6dd50acf2db9cd98650b138c7c341f6fe28fcb91`.
- Post-merge CI run #74 succeeded.
- No open pull requests were present at this coordination checkpoint.

## Remaining M3 issues

- #19 — normalize Bet365/Sportradar prematch market semantics — READY / highest priority.
- #15 — add a second permitted prematch source — READY in parallel.
- #17 — canonical prematch market/selection matching — READY for synthetic implementation because #14/#16 are complete; real-source acceptance depends on #15 and #19.
- #18 — two-source end-to-end QA reconciliation — BLOCKED until #15, #17, and #19 complete.

## Coordination decision

Issue #19 is the next single highest-priority task. The first reference connector still has a known market/selection semantic-token conformance gap; resolving that correctness issue takes precedence over treating more source data as canonical matching evidence.

Issue #15 should follow or proceed in parallel to reduce external-source lead-time risk. Backend issue #17 may independently begin its synthetic structural matching implementation, but final M3 acceptance must use conforming fixtures from #19 and the second source from #15.

## Integration constraint

Only permitted prematch integration methods may be used. No agent may bypass CAPTCHAs, authentication/authorization controls, anti-bot systems, rate limits, geo-restrictions, or other access controls. Direct Bet365 extraction remains out of scope; the existing reference connector uses the documented Sportradar provider boundary.
