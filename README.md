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

## Architecture status

The initial architecture baseline is defined. The project uses a Python modular-monolith design with PostgreSQL as the source of truth. Bookmaker-specific structures are isolated behind connector/adapters and must not leak into core domain/application layers.

Start with:
- `roadmap.md` for milestones and sequencing;
- `backlog.md` for current priorities and dependencies;
- `docs/architecture.md` for system boundaries;
- `docs/data-model.md` for normalized entities;
- `docs/integrations.md` for connector/resilience rules;
- `specs/connector-contract.md` for the mandatory connector contract;
- `AGENTS.md` for autonomous team coordination.

## Current priority

The highest-priority implementation task is GitHub issue #1: bootstrap the normalized domain and PostgreSQL persistence foundation. Broad bookmaker integration remains blocked until the shared implementation contracts are in place.

## Integration policy

Only permitted integration methods may be used, including official APIs, documented feeds, licensed providers, or publicly accessible endpoints where automated access is allowed.

Do not bypass CAPTCHAs, authentication/authorization controls, anti-bot systems, rate limits, geo-restrictions, or other access controls.
