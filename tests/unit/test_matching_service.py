from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from odds_aggregator.matching.models import (
    CompetitionCandidate,
    CompetitionInput,
    EventCandidate,
    EventInput,
    MatchState,
    ParticipantCandidate,
    ParticipantInput,
)
from odds_aggregator.matching.service import (
    DecisionDraft,
    PersistenceResult,
    PrematchMatchingService,
)

SPORT = UUID("00000000-0000-0000-0000-000000000001")
BOOK_A = UUID("00000000-0000-0000-0000-0000000000a1")
BOOK_B = UUID("00000000-0000-0000-0000-0000000000b1")
CANONICAL = UUID("00000000-0000-0000-0000-000000000101")
NOW = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)


class FakeStore:
    def __init__(self) -> None:
        self.mappings: dict[tuple[UUID, str, str], UUID] = {}
        self.competitions: tuple[CompetitionCandidate, ...] = ()
        self.participants: tuple[ParticipantCandidate, ...] = ()
        self.events: tuple[EventCandidate, ...] = ()
        self.decisions: dict[str, UUID] = {}
        self.persist_calls = 0

    def lookup_mapping(
        self, *, bookmaker_id: UUID, entity_type: str, source_id: str
    ) -> UUID | None:
        return self.mappings.get((bookmaker_id, entity_type, source_id))

    def competition_candidates(self, *, sport_id: UUID) -> tuple[CompetitionCandidate, ...]:
        return tuple(candidate for candidate in self.competitions if candidate.sport_id == sport_id)

    def participant_candidates(self, *, sport_id: UUID) -> tuple[ParticipantCandidate, ...]:
        return tuple(candidate for candidate in self.participants if candidate.sport_id == sport_id)

    def event_candidates(
        self,
        *,
        sport_id: UUID,
        start_time: datetime,
        guard_window: timedelta,
    ) -> tuple[EventCandidate, ...]:
        return tuple(
            candidate
            for candidate in self.events
            if candidate.sport_id == sport_id
            and abs(candidate.start_time - start_time) <= guard_window
        )

    def persist_competition(
        self,
        *,
        bookmaker_id: UUID,
        bookmaker_code: str,
        source: CompetitionInput,
        plan,
        decision: DecisionDraft,
    ) -> PersistenceResult:
        return self._persist(bookmaker_id, "competition", source.source_id, plan, decision)

    def persist_participant(
        self,
        *,
        bookmaker_id: UUID,
        bookmaker_code: str,
        source: ParticipantInput,
        plan,
        decision: DecisionDraft,
    ) -> PersistenceResult:
        return self._persist(bookmaker_id, "participant", source.source_id, plan, decision)

    def persist_event(
        self,
        *,
        bookmaker_id: UUID,
        source: EventInput,
        plan,
        decision: DecisionDraft,
    ) -> PersistenceResult:
        return self._persist(bookmaker_id, "event", source.source_id, plan, decision)

    def _persist(self, bookmaker_id, entity_type, source_id, plan, decision):
        self.persist_calls += 1
        decision_id = UUID(int=len(self.decisions) + 100)
        decision_id = self.decisions.setdefault(decision.decision_key, decision_id)
        if plan.state in {MatchState.MATCHED, MatchState.CREATED}:
            assert plan.canonical_id is not None
            self.mappings[(bookmaker_id, entity_type, source_id)] = plan.canonical_id
        return PersistenceResult(plan.canonical_id, decision_id)


def test_mapping_reuse_bypasses_scoring_and_decision() -> None:
    store = FakeStore()
    store.mappings[(BOOK_A, "competition", "source-1")] = CANONICAL
    service = PrematchMatchingService(store, now=lambda: NOW)
    result = service.resolve_competition(
        bookmaker_id=BOOK_A,
        bookmaker_code="book-a",
        source=CompetitionInput("source-1", SPORT, "Different Name"),
    )
    assert result.state is MatchState.REUSED
    assert result.canonical_id == CANONICAL
    assert store.persist_calls == 0
    assert not store.decisions


def test_ambiguous_replay_reuses_decision_key_without_mapping() -> None:
    store = FakeStore()
    store.participants = (
        ParticipantCandidate(CANONICAL, SPORT, "United City", "team"),
        ParticipantCandidate(UUID(int=258), SPORT, "United-City", "team"),
    )
    service = PrematchMatchingService(store, now=lambda: NOW)
    source = ParticipantInput("source-x", SPORT, "United City", "team")

    first = service.resolve_participant(
        bookmaker_id=BOOK_A,
        bookmaker_code="book-a",
        source=source,
    )
    replay = service.resolve_participant(
        bookmaker_id=BOOK_A,
        bookmaker_code="book-a",
        source=source,
    )

    assert first.state is MatchState.AMBIGUOUS
    assert replay.state is MatchState.AMBIGUOUS
    assert first.decision_key == replay.decision_key
    assert first.decision_id == replay.decision_id
    assert (BOOK_A, "participant", "source-x") not in store.mappings
    assert len(store.decisions) == 1


def test_created_resolution_is_deterministic_and_then_reused() -> None:
    store = FakeStore()
    service = PrematchMatchingService(store, now=lambda: NOW)
    source = ParticipantInput("new-participant", SPORT, "Alpha", "team")

    first = service.resolve_participant(
        bookmaker_id=BOOK_A,
        bookmaker_code="book-a",
        source=source,
    )
    replay = service.resolve_participant(
        bookmaker_id=BOOK_A,
        bookmaker_code="book-a",
        source=source,
    )

    assert first.state is MatchState.CREATED
    assert first.canonical_id is not None
    assert replay.state is MatchState.REUSED
    assert replay.canonical_id == first.canonical_id
    assert len(store.decisions) == 1


def test_equal_source_id_across_bookmakers_is_not_identity_shortcut() -> None:
    store = FakeStore()
    service = PrematchMatchingService(store, now=lambda: NOW)
    first = service.resolve_participant(
        bookmaker_id=BOOK_A,
        bookmaker_code="book-a",
        source=ParticipantInput("shared-provider-id", SPORT, "Alpha", "team"),
    )
    second = service.resolve_participant(
        bookmaker_id=BOOK_B,
        bookmaker_code="book-b",
        source=ParticipantInput("shared-provider-id", SPORT, "Completely Different", "team"),
    )

    assert first.state is MatchState.CREATED
    assert second.state is MatchState.CREATED
    assert first.canonical_id != second.canonical_id
