# OddsAggregator

OddsAggregator is a multi-bookmaker betting-odds aggregation platform.

It collects bookmaker/provider sports, competitions, events, participants, markets, selections, odds, and related metadata through permitted integration methods, then normalizes that data into a common bookmaker-agnostic model.

The normalized platform is intended to support:
- odds comparison;
- historical odds;
- arbitrage detection;
- line-movement analysis;
- alerts;
- analytics.

## Architecture and implementation status

The architecture baseline and first production foundation are complete. The project uses a Python modular-monolith design with PostgreSQL as the source of truth. Bookmaker-specific structures are isolated behind connectors and must not leak into core domain/application layers.

Completed foundations include:
- normalized domain and PostgreSQL persistence;
- shared connector DTOs, errors, rate-limit/retry/circuit primitives, and runtime isolation;
- deterministic/idempotent connector-to-canonical ingestion;
- append-only historical odds observations;
- GitHub Actions CI with Ruff, strict mypy, PostgreSQL/Alembic, and pytest;
- first permitted reference connector: Bet365 through Sportradar Odds Comparison Prematch v2;
- end-to-end fixture-based connector -> ingestion -> canonical PostgreSQL validation.

The Bet365 connector does not scrape or automate Bet365 properties. Its documented permitted boundary is Sportradar and its current scope is prematch-only; see `docs/bookmakers/bet365.md`.

Start with:
- `roadmap.md` for milestones and sequencing;
- `backlog.md` for current priorities and dependencies;
- `docs/architecture.md` for system boundaries;
- `docs/data-model.md` for normalized entities;
- `docs/integrations.md` for connector/resilience rules;
- `specs/connector-contract.md` for the mandatory connector contract;
- `docs/ingestion.md` for the production ingestion path;
- `docs/development.md` for local Python/PostgreSQL setup and verification;
- `AGENTS.md` for autonomous team coordination.

## Current priority

Milestone M3 — multi-source normalization and matching — is now in progress.

The highest-priority task is issue #14: define the implementation-ready cross-source matching and canonicalization contract. Issue #15, adding a second permitted source for realistic multi-source validation, is also ready and may proceed in parallel. Backend matching issues #16 and #17 follow the architecture contract, and QA issue #18 validates the complete two-source reconciliation path.

## Integration policy

Only permitted integration methods may be used, including official APIs, documented feeds, licensed providers, or publicly accessible endpoints where automated access is allowed.

Do not bypass CAPTCHAs, authentication/authorization controls, anti-bot systems, rate limits, geo-restrictions, or other access controls.
