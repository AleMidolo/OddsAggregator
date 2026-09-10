from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from odds_aggregator.domain.canonical_ids import canonical_entity_id

from .fingerprints import (
    competition_fingerprint,
    decision_key,
    event_fingerprint,
    participant_fingerprint,
)
from .models import (
    RULE_VERSION,
    CandidateEvidence,
    CompetitionCandidate,
    CompetitionInput,
    DecisionPlan,
    EventCandidate,
    EventInput,
    MatchOutcome,
    MatchState,
    ParticipantCandidate,
    ParticipantInput,
)
from .scoring import decide_competition, decide_event, decide_participant, event_windows_seconds


@dataclass(frozen=True, slots=True)
class DecisionDraft:
    bookmaker_id: UUID
    entity_type: str
    source_id: str
    source_fingerprint: str
    rule_version: str
    decision_key: str
    state: MatchState
    canonical_id: UUID | None
    reason_code: str
    best_score: Decimal | None
    runner_up_score: Decimal | None
    evidence: dict[str, object]
    candidates: tuple[CandidateEvidence, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PersistenceResult:
    canonical_id: UUID | None
    decision_id: UUID | None
    reused_mapping: bool = False


class MatchingStore(Protocol):
    def lookup_mapping(
        self, *, bookmaker_id: UUID, entity_type: str, source_id: str
    ) -> UUID | None: ...

    def competition_candidates(self, *, sport_id: UUID) -> tuple[CompetitionCandidate, ...]: ...

    def participant_candidates(self, *, sport_id: UUID) -> tuple[ParticipantCandidate, ...]: ...

    def event_candidates(
        self,
        *,
        sport_id: UUID,
        start_time: datetime,
        guard_window: timedelta,
    ) -> tuple[EventCandidate, ...]: ...

    def persist_competition(
        self,
        *,
        bookmaker_id: UUID,
        bookmaker_code: str,
        source: CompetitionInput,
        plan: DecisionPlan,
        decision: DecisionDraft,
    ) -> PersistenceResult: ...

    def persist_participant(
        self,
        *,
        bookmaker_id: UUID,
        bookmaker_code: str,
        source: ParticipantInput,
        plan: DecisionPlan,
        decision: DecisionDraft,
    ) -> PersistenceResult: ...

    def persist_event(
        self,
        *,
        bookmaker_id: UUID,
        source: EventInput,
        plan: DecisionPlan,
        decision: DecisionDraft,
    ) -> PersistenceResult: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PrematchMatchingService:
    def __init__(
        self,
        store: MatchingStore,
        *,
        now: Callable[[], datetime] | None = None,
        rule_version: str = RULE_VERSION,
    ) -> None:
        self._store = store
        self._now = now or _utc_now
        self._rule_version = rule_version

    def resolve_competition(
        self,
        *,
        bookmaker_id: UUID,
        bookmaker_code: str,
        source: CompetitionInput,
    ) -> MatchOutcome:
        existing = self._store.lookup_mapping(
            bookmaker_id=bookmaker_id,
            entity_type="competition",
            source_id=source.source_id,
        )
        if existing is not None:
            return MatchOutcome(MatchState.REUSED, existing, "mapping_reused")

        plan = decide_competition(
            source,
            self._store.competition_candidates(sport_id=source.sport_id),
        )
        canonical_id = self._accepted_canonical_id(
            bookmaker_id=bookmaker_id,
            entity_type="competition",
            source_id=source.source_id,
            plan=plan,
        )
        plan = self._with_canonical(plan, canonical_id)
        fingerprint = competition_fingerprint(source)
        draft = self._decision(
            bookmaker_id=bookmaker_id,
            entity_type="competition",
            source_id=source.source_id,
            fingerprint=fingerprint,
            plan=plan,
        )
        persisted = self._store.persist_competition(
            bookmaker_id=bookmaker_id,
            bookmaker_code=bookmaker_code,
            source=source,
            plan=plan,
            decision=draft,
        )
        return self._outcome(plan, draft, persisted)

    def resolve_participant(
        self,
        *,
        bookmaker_id: UUID,
        bookmaker_code: str,
        source: ParticipantInput,
    ) -> MatchOutcome:
        existing = self._store.lookup_mapping(
            bookmaker_id=bookmaker_id,
            entity_type="participant",
            source_id=source.source_id,
        )
        if existing is not None:
            return MatchOutcome(MatchState.REUSED, existing, "mapping_reused")

        plan = decide_participant(
            source,
            self._store.participant_candidates(sport_id=source.sport_id),
        )
        canonical_id = self._accepted_canonical_id(
            bookmaker_id=bookmaker_id,
            entity_type="participant",
            source_id=source.source_id,
            plan=plan,
        )
        plan = self._with_canonical(plan, canonical_id)
        fingerprint = participant_fingerprint(source)
        draft = self._decision(
            bookmaker_id=bookmaker_id,
            entity_type="participant",
            source_id=source.source_id,
            fingerprint=fingerprint,
            plan=plan,
        )
        persisted = self._store.persist_participant(
            bookmaker_id=bookmaker_id,
            bookmaker_code=bookmaker_code,
            source=source,
            plan=plan,
            decision=draft,
        )
        return self._outcome(plan, draft, persisted)

    def resolve_event(
        self,
        *,
        bookmaker_id: UUID,
        source: EventInput,
    ) -> MatchOutcome:
        existing = self._store.lookup_mapping(
            bookmaker_id=bookmaker_id,
            entity_type="event",
            source_id=source.source_id,
        )
        if existing is not None:
            return MatchOutcome(MatchState.REUSED, existing, "mapping_reused")

        _, guard_seconds = event_windows_seconds(source.sport_code)
        candidates = self._store.event_candidates(
            sport_id=source.sport_id,
            start_time=source.start_time,
            guard_window=timedelta(seconds=guard_seconds),
        )
        plan = decide_event(source, candidates)
        canonical_id = self._accepted_canonical_id(
            bookmaker_id=bookmaker_id,
            entity_type="event",
            source_id=source.source_id,
            plan=plan,
        )
        plan = self._with_canonical(plan, canonical_id)
        fingerprint = event_fingerprint(source)
        draft = self._decision(
            bookmaker_id=bookmaker_id,
            entity_type="event",
            source_id=source.source_id,
            fingerprint=fingerprint,
            plan=plan,
        )
        persisted = self._store.persist_event(
            bookmaker_id=bookmaker_id,
            source=source,
            plan=plan,
            decision=draft,
        )
        return self._outcome(plan, draft, persisted)

    def _accepted_canonical_id(
        self,
        *,
        bookmaker_id: UUID,
        entity_type: str,
        source_id: str,
        plan: DecisionPlan,
    ) -> UUID | None:
        if plan.state is MatchState.CREATED:
            return canonical_entity_id(bookmaker_id, entity_type, source_id)
        return plan.canonical_id

    @staticmethod
    def _with_canonical(plan: DecisionPlan, canonical_id: UUID | None) -> DecisionPlan:
        return DecisionPlan(
            state=plan.state,
            canonical_id=canonical_id,
            reason_code=plan.reason_code,
            best_score=plan.best_score,
            runner_up_score=plan.runner_up_score,
            evidence=plan.evidence,
            candidates=plan.candidates,
        )

    def _decision(
        self,
        *,
        bookmaker_id: UUID,
        entity_type: str,
        source_id: str,
        fingerprint: str,
        plan: DecisionPlan,
    ) -> DecisionDraft:
        created_at = self._now()
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("matching clock must return a timezone-aware datetime")
        key = decision_key(
            bookmaker_id=bookmaker_id,
            entity_type=entity_type,
            source_id=source_id,
            source_fingerprint=fingerprint,
            rule_version=self._rule_version,
        )
        return DecisionDraft(
            bookmaker_id=bookmaker_id,
            entity_type=entity_type,
            source_id=source_id,
            source_fingerprint=fingerprint,
            rule_version=self._rule_version,
            decision_key=key,
            state=plan.state,
            canonical_id=plan.canonical_id,
            reason_code=plan.reason_code,
            best_score=plan.best_score,
            runner_up_score=plan.runner_up_score,
            evidence=plan.evidence,
            candidates=plan.candidates,
            created_at=created_at,
        )

    @staticmethod
    def _outcome(
        plan: DecisionPlan,
        decision: DecisionDraft,
        persisted: PersistenceResult,
    ) -> MatchOutcome:
        if persisted.reused_mapping:
            return MatchOutcome(MatchState.REUSED, persisted.canonical_id, "mapping_reused")
        return MatchOutcome(
            state=plan.state,
            canonical_id=persisted.canonical_id,
            reason_code=plan.reason_code,
            source_fingerprint=decision.source_fingerprint,
            decision_key=decision.decision_key,
            decision_id=persisted.decision_id,
            best_score=plan.best_score,
            runner_up_score=plan.runner_up_score,
            evidence=plan.evidence,
            candidates=plan.candidates,
        )
