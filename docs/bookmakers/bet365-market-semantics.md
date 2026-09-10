# Bet365 / Sportradar prematch semantic mapping

This document records the provider-specific translation used by the Bet365 connector for Milestone M3 matching. It supplements `docs/bookmakers/bet365.md`; the access method, authentication, entitlement, rate-limit handling, and prematch-only boundary are unchanged.

## Principle

Sportradar display/source text remains in `SourceMarket.name` and `SourceSelection.label`. Matching-relevant fields are populated only when the Sportradar Odds Comparison Prematch v2 contract provides deterministic semantic evidence. Unknown, conflicting, or structurally inconsistent inputs keep canonical semantic fields null so `prematch-v1` can resolve them as unsupported/unresolved instead of guessing.

## Supported market mappings

| Sportradar evidence | Canonical market type | Canonical period | Canonical line |
| --- | --- | --- | --- |
| market name `1x2`, `2way`, or `3way` | `moneyline` | `full_time` | null |
| current documented market ID `1` | `moneyline` | `full_time` | null |
| market name `1x2_half_time` or current documented market ID `60` | `moneyline` | `first_half` | null |
| market name `total` or current documented market ID `18` | `total` | `full_time` | common structured outcome `total` value |
| market name `spread` | `spread` | `full_time` | structured home-side `spread` when home/away values are exact opposites |

When both recognized market-name and supported market-ID evidence are present, they must resolve to the same canonical semantics. A conflict leaves the market unsupported.

Structured provider IDs take precedence over generic display names. Current Prematch v2 IDs whose documented meaning carries a different period, scope, variant, or market structure are explicitly treated as unsupported by this adapter rather than being reinterpreted through a shorter name. For example, ID `225` is `Total (incl. overtime)`, so a payload that presents ID `225` with display name `total` must remain unsupported until the shared model and adapter explicitly represent that overtime variant. The same conservative rule is applied to other documented but currently unsupported IDs covering team totals, half/quarter markets, overtime/extra-innings variants, and period-specific structures.

The reference sanitized fixture intentionally contains `sr:market:3` with name `total`. ID `3` is not used as current-v2 semantic evidence; the explicit fixture/provider name plus consistent structured over/under totals supplies the safe mapping for that legacy fixture. Unknown IDs are not assumed to carry any specific semantics unless supported by explicit provider-name and structural evidence, while known documented incompatible IDs never fall back to the generic name mapping.

## Selection mappings

Selection types are accepted only within a supported market family:

- moneyline: `home`, `away`, `draw`;
- total: `over`, `under`;
- spread: `home`, `away`.

Other provider outcome types remain null as canonical `selection_type` values. Display labels and source IDs remain preserved.

For totals, only the structured outcome `total` field is used as the threshold. If repeated thresholds disagree, the market is not promoted to canonical semantics. For spreads, only the structured outcome `spread` field is used; the market line is the signed home-side value and is accepted only when the away line is its exact opposite. No line is parsed from display text.

## Provider references

The implementation is based on Sportradar Odds Comparison Prematch v2 documentation current at implementation time. The Sport Event Markets endpoint documents market IDs/names and structured outcome fields including `type`, `spread`, `total`, and `handicap`. The Prematch overview documents market IDs and structures, including ID `1` for 1x2, ID `18` for Total, ID `60` for 1st Half - 1x2, and variant/scoped markets such as ID `225` for Total (incl. overtime).

Any expansion of this mapping table requires documented provider semantics plus deterministic fixture tests. Live/in-play markets remain out of scope.
