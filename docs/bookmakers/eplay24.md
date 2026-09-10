# Eplay24 prematch integration

## Decision

Eplay24 is the second bookmaker/source selected for Milestone M3 validation.

The production adapter uses **OddsPapi v5** as the permitted automated access path. It does not scrape or automate E-Play24 web properties.

This route was selected after a stricter acceptance review of the initially explored Sportradar path. E-Play24 publicly documents a Betradar/Sportradar relationship, but the repository has no production Sportradar entitlement and the reviewed public Sportradar material does not identify Eplay24 in a specific configured `Books` feed. That path therefore could not be verified to the standard required by issue #15 and was superseded.

OddsPapi's public bookmaker catalog explicitly lists **Eplay24 IT** among its API-supported sportsbooks, and the catalog links Eplay24 IT to the provider slug `eplay24.it`. OddsPapi also publishes a documented REST API and authentication, error, and rate-limit contracts. This gives the repository a verifiable provider API boundary without accessing E-Play24 directly.

References reviewed on 2026-09-10:

- OddsPapi bookmaker catalog: `https://oddspapi.io/sportsbooks`
- OddsPapi v5 OpenAPI: `https://docs.oddspapi.io/api-reference/openapi.json`
- OddsPapi v5 rate limits: `https://docs.oddspapi.io/en/api-reference/rate-limits`
- OddsPapi v5 errors: `https://docs.oddspapi.io/en/api-reference/errors`
- OddsPapi terms: `https://oddspapi.io/en/legal/terms`

## Authentication and entitlement

OddsPapi v5 documents `apiKey` as query-parameter authentication. The connector accepts the key at construction and adds it only inside the provider HTTP client; credentials are never placed in DTO metadata, fixtures, logs, or repository configuration.

`health()` requests `/bookmakers?bookmakers=eplay24.it` and returns healthy only when the key's bookmaker catalog contains an active `eplay24.it` entry. A missing or inactive entry is a configuration error rather than an invitation to fall back to scraping.

Production therefore requires an OddsPapi plan/API key whose catalog exposes active Eplay24 IT coverage.

## Usage terms

OddsPapi's current terms allow use of its API but prohibit reselling, repackaging, or redistributing its data as a standalone product and prohibit misuse such as key sharing, limit abuse, or scraping the API. OddsAggregator must be operated within the user's applicable OddsPapi plan and terms. If a future product distributes raw provider data as a standalone feed, commercial permission must be confirmed before release.

The connector does not implement any mechanism to evade provider quotas or access controls.

## Rate limits and failures

The documented v5 per-key limits reviewed for this integration are:

- high-frequency odds endpoints including `GET /fixtures/odds`: **10 requests/second**;
- all other endpoints used here: **200 requests/minute**.

OddsPapi documents `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` response headers and `Retry-After` on HTTP 429. The adapter maps 429 to the shared retryable `ConnectorRateLimitedError` and preserves `Retry-After` when supplied. The shared runtime remains responsible for retry/backoff/rate scheduling.

HTTP failures map to the shared taxonomy:

- 401 -> authentication error;
- 403 -> authorization error;
- 429 -> rate-limit error;
- 408/504 -> timeout error;
- 5xx -> temporary-unavailable error;
- malformed JSON/root schemas -> schema error;
- other client/request errors -> configuration error.

## Prematch-only data flow

The adapter uses the documented v5 resources:

1. `GET /bookmakers` to validate active Eplay24 coverage;
2. `GET /sports` for provider sports;
3. `GET /fixtures` filtered by sport/tournament, Eplay24 mapping, and optional lower scheduled-time bound;
4. local fixture rejection unless provider lifecycle `statusId == 0` and `live == false`;
5. `GET /fixtures/odds?fixtureId=...&bookmakers=eplay24.it` for current Eplay24 prices;
6. `GET /markets?marketIds=...` for structured market/outcome definitions.

OddsPapi documents lifecycle status ID `0` as pregame and `1` as live. The connector branches on the numeric status, not translated labels. It never requests or returns live/in-play data. The fixture endpoint's public v5 schema does not currently expose `statusId` as a documented query parameter, so the connector does not invent one; it enforces the prematch boundary on returned structured status data.

The current shared `EventFeedRequest` has only a lower `since` bound and no upper time bound. When supplied, `since` is sent as OddsPapi `startTimeFrom` epoch seconds. Pagination/cursors are not invented where the v5 endpoint does not document them; a non-null connector cursor is rejected as configuration input.

## Event normalization

Provider IDs remain source identity, never canonical identity:

- `fixtureId` -> `SourceEvent.source_id`;
- `sportId` -> `SourceSport.source_id` / event sport source ID;
- `tournamentId` -> competition source ID;
- participant1/participant2 IDs -> participant source IDs;
- native `bookmakerFixtureId` -> bounded event/market metadata.

Scheduled `startTime` is converted from provider epoch seconds to timezone-aware UTC.

OddsPapi identifies participants as participant 1 and participant 2. The event adapter preserves those as deterministic positions `1` and `2` rather than inventing bookmaker-specific role labels. Participant names come only from structured provider fields.

## Market and selection normalization

OddsPapi v5 market definitions expose structured `marketType`, `period`, `handicap`, and canonical outcome IDs/names. Each line is represented by its own frozen market ID.

For issue #15 the adapter intentionally promotes only one market family whose semantics are narrow enough for `prematch-v1`:

- `marketType == 1x2`;
- `period == fulltime`;
- not a player prop;
- no non-zero handicap;
- Eplay24 participant ordering is explicitly reported as not rotated.

That evidence maps to canonical `moneyline / full_time`. Outcomes `1`, `X`, and `2` map to `home`, `draw`, and `away`; home/away selections retain the corresponding OddsPapi participant source ID. Native `bookmakerOutcomeId` is preferred as selection source ID, with the provider odds ID retained as provenance.

Other market types remain present with source/display identity and prices but canonical `market_type`/`period` fields stay null until a future provider-specific mapping is documented and fixture-tested. This prevents overtime, period, line, or scope distinctions from collapsing into unsupported M3 keys.

A market is suspended when the Eplay24 fixture is suspended or provider quote evidence reports `marketActive == false`. Unavailable/suspended selections keep `decimal_odds = null` rather than exposing stale odds as available.

## Cross-source test policy

CI is deterministic and network-free. Sanitized Eplay24 fixtures intentionally use source fixture, competition, participant, market, and outcome identifiers different from the Bet365/Sportradar reference fixture. The event start differs by two minutes and participant display punctuation differs while `prematch-v1` name normalization produces the same names.

The test therefore demonstrates that the fixture is suitable for real cross-source participant/event/market reconciliation without relying on equal upstream source IDs.

All Eplay24 native IDs in `tests/fixtures/eplay24_oddspapi/` are synthetic test values and must not be treated as production bookmaker identifiers.
