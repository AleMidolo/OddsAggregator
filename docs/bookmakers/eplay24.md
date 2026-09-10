# Eplay24 prematch integration

## Decision

Eplay24 is the second bookmaker/source for Milestone M3 validation.

The adapter does **not** scrape or automate E-Play24 web properties. It uses the documented, authenticated Sportradar Odds Comparison Prematch v2 API through a legitimate Odds Comparison Core/bookmaker entitlement.

E-Play24's own corporate material states that Betradar is the Sportradar brand through which E-Play24 offers pre-match odds, and that E-Play24's internal traders elaborate the offered odds so they may differ from other bookmakers. Sportradar documents Odds Comparison Core as its global tier with 140+ bookmakers, configured by Sportradar Support at API-key level, and documents the Prematch `Books` endpoint as the source of the bookmakers and IDs configured for a key.

Provider references reviewed on 2026-09-10:

- E-Play24 company page: `https://www.e-play24.com/lazienda/?lang=en`
- Sportradar Odds Comparison Core release/entitlement documentation: `https://developer.sportradar.com/sportradar-updates/changelog/odds-comparison-core-release`
- Sportradar Odds Comparison Prematch Books endpoint: `https://developer.sportradar.com/odds/reference/oc-prematch-books`

## Entitlement and book identity

The repository and CI intentionally contain no production Sportradar API key, so implementation-time CI cannot query an operator's configured `Books` feed. Public documentation reviewed for this issue does not publish a stable E-Play24 numeric book ID. The connector therefore does not invent or hard-code one.

Production configuration works as follows:

1. obtain a legitimate Sportradar Odds Comparison key with Odds Comparison Core and Eplay24/book access enabled;
2. call the documented Prematch `Books` feed using that key;
3. configure `eplay24_book_id` with the exact Eplay24 ID returned by that feed when available;
4. instantiate `Eplay24SportradarConnector` with the same key/access level;
5. run `health()`, which re-queries `books.json` and reports `configuration_error` unless the configured Eplay24 identity is actually exposed by the key.

When no explicit ID is supplied, `health()` may match the documented E-Play24 brand name using punctuation-insensitive comparison (`E-Play24` / `Eplay24`). Once an operator has observed the provider's exact book ID, explicit ID configuration is preferred and authoritative.

The fixture ID `sr:book:999999` is synthetic test data only and **must not** be copied into production configuration.

## Authentication and transport

The connector reuses the existing `SportradarPrematchClient`:

- authentication header: `x-api-key`;
- access levels: `trial` or `production` as supported by Sportradar;
- explicit HTTP timeout;
- `401` -> shared authentication error;
- `403` -> shared authorization error;
- `429` -> shared rate-limit error, preserving `Retry-After` when supplied;
- `408` / `504` -> shared timeout error;
- `5xx` -> shared temporary-unavailable error;
- malformed JSON/schema roots -> shared schema error.

No static request quota is hard-coded because the reviewed public material does not establish an Eplay24-specific rate value. Runtime `429`/`Retry-After` behavior is respected by the existing transport and shared resilience layer.

## Prematch data flow

The adapter uses only the existing documented Prematch v2 paths already supported by the reference connector:

- `books.json` for entitlement validation;
- `sports.json` for sports;
- sport/competition schedule feeds for prematch events;
- `sport_events/{id}/sport_event_markets.json?live=false` for prematch markets.

Live/in-play products and endpoints remain out of scope.

## Normalization

Because both Bet365 and Eplay24 are consumed through Sportradar Odds Comparison, Eplay24 reuses the conservative, documented Sportradar market semantic translation accepted for issue #19:

- supported 1x2/2way/3way evidence -> `moneyline/full_time`;
- supported Total evidence -> `total/full_time` only with one consistent structured threshold;
- supported Spread evidence -> `spread/full_time` only with one unique home line and one exact-opposite away line;
- supported half-time 1x2 evidence -> `moneyline/first_half`;
- documented incompatible period/scope/variant IDs remain unsupported/null rather than collapsing through generic names.

Source display names, source identifiers, decimal odds, timestamps, suspension/unavailability, and bookmaker external event/market IDs remain preserved. Eplay24-specific metadata uses `eplay24_external_event_id` and `eplay24_external_market_id` rather than Bet365 metadata keys.

## Cross-source fixture policy

The Eplay24 fixtures are sanitized and intentionally use different source sport, competition, event, participant, market, and outcome identifiers from the Bet365 fixture, plus small participant-name and start-time variations. This prevents M3 validation from succeeding merely because both connectors use the same upstream provider identity.

Those deliberately divergent fixture IDs are test evidence for canonical reconciliation and are **not** a statement that Sportradar normally assigns different event IDs to each bookmaker.

CI is fixture/mock-only and never calls Sportradar or E-Play24 live services.
