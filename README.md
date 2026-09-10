# OddsAggregator

OddsAggregator is a multi-bookmaker **prematch** betting-odds aggregation platform.

It collects bookmaker/provider sports, competitions, events, participants, markets, selections, prematch odds, and related metadata through permitted integration methods, then normalizes that data into a common bookmaker-agnostic model.

**Product scope is prematch-only. Live/in-play matches and live/in-play odds are not part of the product roadmap and must not be implemented unless the product scope is explicitly changed in the future.**

The normalized platform is intended to support:
- prematch odds comparison;
- historical prematch odds;
- prematch arbitrage detection;
- prematch line-movement analysis;
- alerts;
- analytics.

## Architecture and implementation status

Milestones M0, M1, and M2 are complete. Milestone M3 — multi-source prematch normalization and matching — is in progress.

Completed foundations include:
- normalized domain and PostgreSQL persistence;
- shared connector DTOs, errors, rate-limit/retry/circuit primitives, and runtime isolation;
- deterministic/idempotent connector-to-canonical ingestion;
- append-only historical odds observations;
- GitHub Actions CI with Ruff, strict mypy, PostgreSQL/Alembic, and pytest;
- first permitted reference connector: Bet365 through Sportradar Odds Comparison Prematch v2;
- authoritative `prematch-v1` cross-source matching contract and ADR 0002;
- production competition/participant/event matching integrated into `ConnectorIngestionService`;
- Bet365/Sportradar competition and participant identity evidence preserved for M3 matching.

The Bet365 connector does not scrape or automate Bet365 properties. Its documented permitted boundary is Sportradar and its scope is prematch-only; see `docs/bookmakers/bet365.md`.

Start with:
- `roadmap.md` for milestones and sequencing;
- `backlog.md` for current priorities and dependencies;
- `specs/prematch-matching.md` for authoritative M3 matching rules;
- `docs/architecture.md` and ADRs for system boundaries and decisions;
- `docs/data-model.md` for normalized entities;
- `docs/integrations.md` for connector/resilience rules;
- `specs/connector-contract.md` for the mandatory connector contract;
- `docs/ingestion.md` for the production ingestion path;
- `AGENTS.md` for autonomous team coordination.

## Current priority

The current highest-priority task is **issue #19: normalize Bet365/Sportradar prematch market semantics for M3 matching**. The existing reference connector must emit controlled canonical market/selection semantic tokens before its market fixtures are safe cross-source evidence.

Issue #15, adding a second permitted prematch source, is also ready and may proceed in parallel. Issue #17 can begin synthetic structural market/selection matching now that #14 and #16 are complete, but its real-source M3 acceptance depends on both #15 and #19. Issue #18 remains blocked until #15, #17, and #19 are complete.

## Integration policy

Only permitted integration methods may be used, including official APIs, documented feeds, licensed providers, or publicly accessible endpoints where automated access is allowed.

Do not bypass CAPTCHAs, authentication/authorization controls, anti-bot systems, rate limits, geo-restrictions, or other access controls.
