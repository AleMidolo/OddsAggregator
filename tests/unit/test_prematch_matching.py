from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from odds_aggregator.matching.models import (
    CompetitionCandidate,
    CompetitionInput,
    EventCandidate,
    EventInput,
    EventParticipantCandidate,
    EventParticipantInput,
    MatchState,
    ParticipantCandidate,
    ParticipantInput,
)
from odds_aggregator.matching.normalization import name_similarity, normalize_name, normalize_season
from odds_aggregator.matching.scoring import decide_competition, decide_event, decide_participant

SPORT = UUID("00000000-0000-0000-0000-000000000001")
A = UUID("00000000-0000-0000-0000-00000000000a")
B = UUID("00000000-0000-0000-0000-00000000000b")
C = UUID("00000000-0000-0000-0000-00000000000c")
D = UUID("00000000-0000-0000-0000-00000000000d")


def test_normalization_contract() -> None:
    assert normalize_name("  Paris—Saint‑Germain FC ") == "paris saint germain fc"
    assert name_similarity("Catania", "Catanìa") == Decimal("0.98")
    assert normalize_season("2026/27") == "2026-2027"
    assert normalize_season("1999–00") == "1999-2000"


def test_competition_auto_match_and_conflict_create() -> None:
    candidate = CompetitionCandidate(
        id=A,
        sport_id=SPORT,
        name="Serie A",
        country_code="IT",
        season="2026-2027",
    )
    matched = decide_competition(
        CompetitionInput(
            source_id="league-1",
            sport_id=SPORT,
            name="SERIE-A",
            country_code="it",
            season="2026/27",
        ),
        (candidate,),
    )
    assert matched.state is MatchState.MATCHED
    assert matched.canonical_id == A

    created = decide_competition(
        CompetitionInput(
            source_id="league-2",
            sport_id=SPORT,
            name="Serie A",
            country_code="BR",
            season="2026-2027",
        ),
        (candidate,),
    )
    assert created.state is MatchState.CREATED
    assert created.evidence["hard_rejection_count"] == 1


def test_participant_alias_auto_match_and_ambiguity() -> None:
    alias_candidate = ParticipantCandidate(
        id=A,
        sport_id=SPORT,
        name="Internazionale Milano",
        participant_type="team",
        aliases=("Inter",),
    )
    result = decide_participant(
        ParticipantInput(
            source_id="participant-1",
            sport_id=SPORT,
            name="Inter",
            participant_type="team",
        ),
        (alias_candidate,),
    )
    assert result.state is MatchState.MATCHED

    candidates = (
        ParticipantCandidate(
            id=A,
            sport_id=SPORT,
            name="United City",
            participant_type="team",
        ),
        ParticipantCandidate(
            id=B,
            sport_id=SPORT,
            name="United-City",
            participant_type="team",
        ),
    )
    ambiguous = decide_participant(
        ParticipantInput(
            source_id="participant-2",
            sport_id=SPORT,
            name="United City",
            participant_type="team",
        ),
        candidates,
    )
    assert ambiguous.state is MatchState.AMBIGUOUS
    assert ambiguous.reason_code == "insufficient_margin"


def _event_candidate(start: datetime, *, reverse: bool = False) -> EventCandidate:
    first, second = (B, A) if reverse else (A, B)
    return EventCandidate(
        id=C,
        sport_id=SPORT,
        start_time=start,
        name="Alpha v Beta",
        participants=(
            EventParticipantCandidate(first, role="home"),
            EventParticipantCandidate(second, role="away"),
        ),
    )


def _event_source(start: datetime) -> EventInput:
    return EventInput(
        source_id="event-source",
        sport_id=SPORT,
        sport_code="football",
        start_time=start,
        name="Alpha - Beta",
        participants=(
            EventParticipantInput("a", A, role="home"),
            EventParticipantInput("b", B, role="away"),
        ),
    )


def test_event_auto_match_reversal_guard_and_create() -> None:
    start = datetime(2026, 9, 12, 18, tzinfo=UTC)
    matched = decide_event(_event_source(start), (_event_candidate(start + timedelta(minutes=5)),))
    assert matched.state is MatchState.MATCHED
    assert matched.canonical_id == C

    reversal = decide_event(_event_source(start), (_event_candidate(start, reverse=True),))
    assert reversal.state is MatchState.AMBIGUOUS
    assert reversal.reason_code == "duplicate_risk_role_conflict"

    guard = decide_event(
        _event_source(start),
        (_event_candidate(start + timedelta(minutes=31)),),
    )
    assert guard.state is MatchState.AMBIGUOUS
    assert guard.reason_code == "duplicate_risk_time_window"

    outside = decide_event(
        _event_source(start),
        (_event_candidate(start + timedelta(hours=25)),),
    )
    assert outside.state is MatchState.CREATED


def test_live_and_parent_failures_do_not_match() -> None:
    start = datetime(2026, 9, 12, 18, tzinfo=UTC)
    live = EventInput(
        source_id="live",
        sport_id=SPORT,
        sport_code="football",
        start_time=start,
        is_live=True,
        participants=(
            EventParticipantInput("a", A),
            EventParticipantInput("b", B),
        ),
    )
    assert decide_event(live, ()).state is MatchState.REJECTED

    unresolved = EventInput(
        source_id="missing-parent",
        sport_id=SPORT,
        sport_code="football",
        start_time=start,
        participants=(
            EventParticipantInput("a", A),
            EventParticipantInput("b", None),
        ),
    )
    assert decide_event(unresolved, ()).state is MatchState.UNRESOLVED
