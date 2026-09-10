from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from odds_aggregator.connectors import EventFeedRequest
from odds_aggregator.connectors.bet365 import Bet365SportradarConnector
from odds_aggregator.connectors.bet365.connector import JsonResponse

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "bet365_sportradar"


def _fixture(name: str) -> dict[str, object]:
    raw: object = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


class ScheduleClient:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self.payload = payload

    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> JsonResponse:
        assert path.endswith("/schedules.json")
        return JsonResponse(payload=self.payload, headers={})


@pytest.mark.asyncio
async def test_schedule_embeds_structured_competition_and_participant_identity() -> None:
    connector = Bet365SportradarConnector(client=ScheduleClient(_fixture("schedules.json")))

    result = await connector.list_events(
        EventFeedRequest(
            sport_source_id="sr:sport:1",
            since=datetime(2026, 9, 10, tzinfo=UTC),
        )
    )

    event = result.events[0]
    assert event.competition_source_id == "sr:competition:17"
    assert event.competition is not None
    assert event.competition.source_id == "sr:competition:17"
    assert event.competition.sport_source_id == "sr:sport:1"
    assert event.competition.name == "Premier League"

    assert [participant.source_id for participant in event.participants] == [
        "sr:competitor:10",
        "sr:competitor:20",
    ]
    assert [participant.role for participant in event.participants] == ["home", "away"]
    assert [
        participant.participant.name if participant.participant is not None else None
        for participant in event.participants
    ] == ["Alpha FC", "Beta FC"]
    assert all(
        participant.participant is None
        or participant.participant.participant_type is None
        for participant in event.participants
    )


@pytest.mark.asyncio
async def test_missing_structured_names_do_not_become_identity_evidence() -> None:
    payload: dict[str, object] = {
        "generated_at": "2026-09-10T12:00:00Z",
        "schedules": [
            {
                "sport_event": {
                    "id": "sr:sport_event:missing-names",
                    "start_time": "2026-09-10T18:45:00Z",
                    "status": "not_started",
                    "competitors": [
                        {
                            "id": "sr:competitor:missing-name",
                            "qualifier": "home",
                        },
                        {
                            "id": "sr:competitor:20",
                            "name": "Beta FC",
                            "qualifier": "away",
                        },
                    ],
                    "sport_event_context": {
                        "sport": {"id": "sr:sport:1", "name": "Soccer"},
                        "competition": {"id": "sr:competition:17"},
                    },
                }
            }
        ],
    }
    connector = Bet365SportradarConnector(client=ScheduleClient(payload))

    result = await connector.list_events(
        EventFeedRequest(
            sport_source_id="sr:sport:1",
            since=datetime(2026, 9, 10, tzinfo=UTC),
        )
    )

    event = result.events[0]
    assert event.competition_source_id == "sr:competition:17"
    assert event.competition is None
    assert event.participants[0].source_id == "sr:competitor:missing-name"
    assert event.participants[0].participant is None
    assert event.participants[1].participant is not None
    assert event.participants[1].participant.name == "Beta FC"
    assert event.name == "Beta FC"
