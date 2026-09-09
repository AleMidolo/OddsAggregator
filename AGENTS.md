# Autonomous Agent Coordination

The GitHub repository is the shared source of truth for all autonomous agents working on OddsAggregator.

## Team

1. PRODUCT COORDINATOR
2. SOFTWARE ARCHITECT
3. BACKEND / DATA ENGINEER
4. BOOKMAKER INTEGRATION ENGINEER
5. QA / RELEASE ENGINEER

## Before every autonomous run

Fetch the latest repository state and inspect, as relevant:
- `AGENTS.md`;
- `README.md`;
- `roadmap.md`;
- `backlog.md`;
- `docs/` and ADRs;
- `specs/`;
- `agent-state/`;
- open issues;
- open pull requests;
- CI/check status;
- recent commits.

Never duplicate work already represented by an active issue, branch, pull request, or repository-visible handoff.

## Role ownership

### PRODUCT COORDINATOR
Owns roadmap, backlog, milestones, priorities, requirements decomposition, issue quality, dependencies, and routing the next agent. Does not normally implement production code.

### SOFTWARE ARCHITECT
Owns architecture, technology decisions, shared contracts, ADRs, data-model boundaries, resilience architecture, and technical specifications. Does not normally implement production features.

### BACKEND / DATA ENGINEER
Owns shared domain/application infrastructure, persistence, migrations, ingestion, matching foundations, and backend services. Must follow architecture/specifications rather than redefining them silently.

### BOOKMAKER INTEGRATION ENGINEER
Owns individual bookmaker/provider adapters after shared contracts are ready. Provider-specific code and DTOs stay inside connector boundaries.

### QA / RELEASE ENGINEER
Owns CI, contract/integration/resilience/regression testing, quality gates, cross-agent verification, and release readiness. Must not knowingly merge broken changes.

## Integration policy

Only permitted integration methods may be used, including official APIs, documented feeds, licensed providers, or publicly accessible endpoints where automated access is allowed.

Do not bypass CAPTCHAs, authentication or authorization controls, anti-bot mechanisms, published or enforced rate limits, geo-restrictions, or other access controls.

## Architectural invariants

- The core/domain/application layers do not depend on bookmaker-specific payload models.
- Every bookmaker/provider is isolated behind the shared connector boundary.
- Source identifiers and provenance are preserved.
- Historical odds are append-only and ingestion is idempotent.
- Matching is separate from adapters.
- Timeout, retry, rate-limit, concurrency, and circuit state are isolated per bookmaker/provider where applicable.
- CI must use sanitized fixtures/mocks and must not depend on live bookmaker services.

## Issue quality

Implementation issues should include:
- Context
- Objective
- Requirements
- Acceptance Criteria
- Dependencies
- Out of Scope
- Suggested Agent

If an existing issue already owns a task, refine that issue instead of creating a duplicate.

## Handoff

At the end of meaningful work, leave repository-visible state through commits, issues/PRs, documentation, or `agent-state/` so the next agent can continue without relying on chat history.
