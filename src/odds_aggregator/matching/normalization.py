from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

_SCORE_QUANTUM = Decimal("0.00001")
_SPACE = re.compile(r"\s+")
_TOKEN_SEPARATOR = re.compile(r"[^\w]+", flags=re.UNICODE)


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value.strip()).casefold()
    pieces: list[str] = []
    pending_space = False
    for char in normalized:
        category = unicodedata.category(char)
        if category[0] in {"P", "S", "Z"} or char.isspace():
            pending_space = bool(pieces)
            continue
        if pending_space:
            pieces.append(" ")
            pending_space = False
        pieces.append(char)
    return "".join(pieces).strip()


def accent_fold(value: str) -> str:
    strict = normalize_name(value)
    decomposed = unicodedata.normalize("NFKD", strict)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    if len(left) > len(right):
        left, right = right, left
    previous = list(range(len(left) + 1))
    for row, right_char in enumerate(right, start=1):
        current = [row]
        for column, left_char in enumerate(left, start=1):
            current.append(
                min(
                    current[column - 1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def token_dice(left: str, right: str) -> Decimal:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens and not right_tokens:
        return Decimal("1")
    denominator = len(left_tokens) + len(right_tokens)
    if denominator == 0:
        return Decimal("0")
    numerator = 2 * len(left_tokens & right_tokens)
    return Decimal(numerator) / Decimal(denominator)


def name_similarity(left: str, right: str) -> Decimal:
    left_strict = normalize_name(left)
    right_strict = normalize_name(right)
    if left_strict == right_strict:
        return Decimal("1")
    if accent_fold(left_strict) == accent_fold(right_strict):
        return Decimal("0.98")
    maximum = max(len(left_strict), len(right_strict))
    levenshtein = Decimal("0")
    if maximum:
        distance = levenshtein_distance(left_strict, right_strict)
        levenshtein = Decimal("1") - Decimal(distance) / Decimal(maximum)
    return min(max(levenshtein, token_dice(left_strict, right_strict)), Decimal("0.97"))


def best_name_similarity(
    source_name: str, canonical_name: str, aliases: tuple[str, ...]
) -> Decimal:
    return max(name_similarity(source_name, candidate) for candidate in (canonical_name, *aliases))


def normalize_country(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if len(normalized) != 2 or not normalized.isalpha() or not normalized.isascii():
        return None
    return normalized


def normalize_season(value: str | None) -> str | None:
    if value is None:
        return None
    raw = "".join(
        "-" if char == "/" or unicodedata.category(char) == "Pd" else char
        for char in value.strip()
    )
    normalized = _SPACE.sub(" ", raw)
    normalized = re.sub(r"\s*-\s*", "-", normalized)
    if not normalized:
        return None
    full = re.fullmatch(r"(\d{4})-(\d{4})", normalized)
    if full is not None:
        return f"{full.group(1)}-{full.group(2)}"
    short = re.fullmatch(r"(\d{4})-(\d{2})", normalized)
    if short is not None:
        first = int(short.group(1))
        suffix = int(short.group(2))
        century = (first // 100) * 100
        second = century + suffix
        if second < first:
            second += 100
        return f"{first:04d}-{second:04d}"
    if re.fullmatch(r"\d{4}", normalized):
        return normalized
    return normalized


def normalize_gender(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _TOKEN_SEPARATOR.sub(
        "_", unicodedata.normalize("NFKC", value).casefold()
    ).strip("_")
    return normalized or None


def normalize_role(value: str | None) -> str | None:
    return normalize_gender(value)


def normalize_participant_type(value: str | None) -> str | None:
    normalized = normalize_role(value)
    if normalized in {"team", "player", "pair", "other"}:
        return normalized
    return None


def metadata_score(
    left: str | None,
    right: str | None,
    *,
    conflict: Decimal = Decimal("0"),
) -> Decimal:
    if left is None or right is None:
        return Decimal("0.5")
    if left == right:
        return Decimal("1")
    return conflict


def rounded_score(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(_SCORE_QUANTUM)
