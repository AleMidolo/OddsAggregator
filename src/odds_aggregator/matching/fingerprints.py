from __future__ import annotations

import hashlib
import json
from datetime import UTC
from uuid import UUID

from .models import CompetitionInput, EventInput, ParticipantInput
from .normalization import (
    normalize_country,
    normalize_gender,
    normalize_name,
    normalize_participant_type,
    normalize_role,
    normalize_season,
)


def _fingerprint(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def competition_fingerprint(value: CompetitionInput) -> str:
    return _fingerprint(
        {
            "sport_id": str(value.sport_id),
            "name": normalize_name(value.name),
            "country": normalize_country(value.country_code),
            "season": normalize_season(value.season),
            "gender": normalize_gender(value.gender),
        }
    )


def participant_fingerprint(value: ParticipantInput) -> str:
    return _fingerprint(
        {
            "sport_id": str(value.sport_id),
            "name": normalize_name(value.name),
            "type": normalize_participant_type(value.participant_type),
            "country": normalize_country(value.country_code),
        }
    )


def event_fingerprint(value: EventInput) -> str:
    participants = [
        {
            "source_id": participant.source_id,
            "canonical_id": (
                None if participant.canonical_id is None else str(participant.canonical_id)
            ),
            "role": normalize_role(participant.role),
            "position": participant.position,
        }
        for participant in value.participants
    ]
    participants.sort(key=lambda item: (str(item["canonical_id"]), str(item["source_id"])))
    return _fingerprint(
        {
            "sport_id": str(value.sport_id),
            "competition_source_id": value.competition_source_id,
            "competition_id": None if value.competition_id is None else str(value.competition_id),
            "participants": participants,
            "start_time": value.start_time.astimezone(UTC).isoformat(timespec="microseconds"),
            "name": None if value.name is None else normalize_name(value.name),
            "out_of_scope_live": (
                value.is_live or normalize_role(value.status) == "live"
            ),
        }
    )


def decision_key(
    *,
    bookmaker_id: UUID,
    entity_type: str,
    source_id: str,
    source_fingerprint: str,
    rule_version: str,
) -> str:
    payload = "|".join(
        (str(bookmaker_id), entity_type, source_id, source_fingerprint, rule_version)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
