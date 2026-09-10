from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from odds_aggregator.matching.models import (
    CompetitionInput,
    DecisionPlan,
    EventInput,
    MatchState,
    ParticipantInput,
)
from odds_aggregator.matching.normalization import (
    normalize_country,
    normalize_gender,
    normalize_name,
    normalize_participant_type,
    normalize_role,
    normalize_season,
)
from odds_aggregator.matching.service import DecisionDraft, PersistenceResult

from .matching_models import MatchCandidateRecord, MatchDecisionRecord
from .matching_queries import MatchingReadMixin
from .models import (
    CompetitionAliasRecord,
    CompetitionRecord,
    EventParticipantRecord,
    EventRecord,
    ParticipantAliasRecord,
    ParticipantRecord,
    SourceEntityMappingRecord,
)

_MATCHING_NAMESPACE = UUID("f55a70c0-2aa2-46bb-963d-70b9b13070fd")
_ACCEPTED_STATES = {MatchState.MATCHED, MatchState.CREATED}


class MatchingWriteMixin(MatchingReadMixin):
    def persist_competition(
        self,
        *,
        bookmaker_id: UUID,
        bookmaker_code: str,
        source: CompetitionInput,
        plan: DecisionPlan,
        decision: DecisionDraft,
    ) -> PersistenceResult:
        with self._session_factory.begin() as session:
            race = self._existing_mapping_result(
                session,
                bookmaker_id=bookmaker_id,
                entity_type="competition",
                source_id=source.source_id,
            )
            if race is not None:
                return race
            if plan.state in _ACCEPTED_STATES:
                canonical_id = self._require_canonical(plan)
                if not self._claim_mapping(
                    session,
                    bookmaker_id=bookmaker_id,
                    entity_type="competition",
                    source_id=source.source_id,
                    canonical_id=canonical_id,
                    source_name=source.name,
                    seen_at=decision.created_at,
                ):
                    return self._mapping_race_result(
                        session,
                        bookmaker_id=bookmaker_id,
                        entity_type="competition",
                        source_id=source.source_id,
                    )
                if plan.state is MatchState.CREATED:
                    session.execute(
                        insert(CompetitionRecord)
                        .values(
                            id=canonical_id,
                            sport_id=source.sport_id,
                            name=source.name,
                            country_code=normalize_country(source.country_code),
                            gender=normalize_gender(source.gender),
                            season=normalize_season(source.season),
                        )
                        .on_conflict_do_nothing(index_elements=["id"])
                    )
                canonical = session.get(CompetitionRecord, canonical_id)
                if canonical is None:
                    raise RuntimeError("competition resolution points to a missing canonical row")
                self._insert_competition_alias(
                    session,
                    competition_id=canonical_id,
                    alias=normalize_name(canonical.name),
                    provenance="canonical",
                )
                self._insert_competition_alias(
                    session,
                    competition_id=canonical_id,
                    alias=normalize_name(source.name),
                    provenance=self._bookmaker_provenance(bookmaker_code),
                )
            decision_id = self._persist_decision(session, decision)
            return PersistenceResult(plan.canonical_id, decision_id)

    def persist_participant(
        self,
        *,
        bookmaker_id: UUID,
        bookmaker_code: str,
        source: ParticipantInput,
        plan: DecisionPlan,
        decision: DecisionDraft,
    ) -> PersistenceResult:
        with self._session_factory.begin() as session:
            race = self._existing_mapping_result(
                session,
                bookmaker_id=bookmaker_id,
                entity_type="participant",
                source_id=source.source_id,
            )
            if race is not None:
                return race
            if plan.state in _ACCEPTED_STATES:
                canonical_id = self._require_canonical(plan)
                if not self._claim_mapping(
                    session,
                    bookmaker_id=bookmaker_id,
                    entity_type="participant",
                    source_id=source.source_id,
                    canonical_id=canonical_id,
                    source_name=source.name,
                    seen_at=decision.created_at,
                ):
                    return self._mapping_race_result(
                        session,
                        bookmaker_id=bookmaker_id,
                        entity_type="participant",
                        source_id=source.source_id,
                    )
                if plan.state is MatchState.CREATED:
                    session.execute(
                        insert(ParticipantRecord)
                        .values(
                            id=canonical_id,
                            sport_id=source.sport_id,
                            type=normalize_participant_type(source.participant_type) or "other",
                            name=source.name,
                            country_code=normalize_country(source.country_code),
                        )
                        .on_conflict_do_nothing(index_elements=["id"])
                    )
                canonical = session.get(ParticipantRecord, canonical_id)
                if canonical is None:
                    raise RuntimeError("participant resolution points to a missing canonical row")
                self._insert_participant_alias(
                    session,
                    participant_id=canonical_id,
                    alias=normalize_name(canonical.name),
                    provenance="canonical",
                )
                self._insert_participant_alias(
                    session,
                    participant_id=canonical_id,
                    alias=normalize_name(source.name),
                    provenance=self._bookmaker_provenance(bookmaker_code),
                )
            decision_id = self._persist_decision(session, decision)
            return PersistenceResult(plan.canonical_id, decision_id)

    def persist_event(
        self,
        *,
        bookmaker_id: UUID,
        source: EventInput,
        plan: DecisionPlan,
        decision: DecisionDraft,
    ) -> PersistenceResult:
        with self._session_factory.begin() as session:
            race = self._existing_mapping_result(
                session,
                bookmaker_id=bookmaker_id,
                entity_type="event",
                source_id=source.source_id,
            )
            if race is not None:
                return race
            if plan.state in _ACCEPTED_STATES:
                canonical_id = self._require_canonical(plan)
                if not self._claim_mapping(
                    session,
                    bookmaker_id=bookmaker_id,
                    entity_type="event",
                    source_id=source.source_id,
                    canonical_id=canonical_id,
                    source_name=source.name,
                    seen_at=decision.created_at,
                ):
                    return self._mapping_race_result(
                        session,
                        bookmaker_id=bookmaker_id,
                        entity_type="event",
                        source_id=source.source_id,
                    )
                if plan.state is MatchState.CREATED:
                    session.execute(
                        insert(EventRecord)
                        .values(
                            id=canonical_id,
                            sport_id=source.sport_id,
                            competition_id=source.competition_id,
                            name=source.name,
                            start_time=source.start_time,
                            status=self._event_status(source.status),
                            is_live=False,
                            created_at=decision.created_at,
                            updated_at=decision.created_at,
                        )
                        .on_conflict_do_nothing(index_elements=["id"])
                    )
                    for participant in source.participants:
                        if participant.canonical_id is None:
                            raise RuntimeError("accepted event has an unresolved participant")
                        session.execute(
                            insert(EventParticipantRecord)
                            .values(
                                event_id=canonical_id,
                                participant_id=participant.canonical_id,
                                role=normalize_role(participant.role),
                                position=participant.position,
                            )
                            .on_conflict_do_nothing(
                                index_elements=["event_id", "participant_id"]
                            )
                        )
                if session.get(EventRecord, canonical_id) is None:
                    raise RuntimeError("event resolution points to a missing canonical row")
            decision_id = self._persist_decision(session, decision)
            return PersistenceResult(plan.canonical_id, decision_id)

    def _existing_mapping_result(
        self,
        session: Session,
        *,
        bookmaker_id: UUID,
        entity_type: str,
        source_id: str,
    ) -> PersistenceResult | None:
        mapping = self._mapping_record(
            session,
            bookmaker_id=bookmaker_id,
            entity_type=entity_type,
            source_id=source_id,
        )
        if mapping is None:
            return None
        return PersistenceResult(mapping.canonical_id, None, reused_mapping=True)

    def _mapping_race_result(
        self,
        session: Session,
        *,
        bookmaker_id: UUID,
        entity_type: str,
        source_id: str,
    ) -> PersistenceResult:
        mapping = self._mapping_record(
            session,
            bookmaker_id=bookmaker_id,
            entity_type=entity_type,
            source_id=source_id,
        )
        if mapping is None:
            raise RuntimeError("source mapping conflict did not produce a reusable mapping")
        return PersistenceResult(mapping.canonical_id, None, reused_mapping=True)

    @staticmethod
    def _claim_mapping(
        session: Session,
        *,
        bookmaker_id: UUID,
        entity_type: str,
        source_id: str,
        canonical_id: UUID,
        source_name: str | None,
        seen_at: datetime,
    ) -> bool:
        mapping_id = uuid5(
            _MATCHING_NAMESPACE,
            f"mapping:{bookmaker_id}:{entity_type}:{source_id}",
        )
        inserted = session.execute(
            insert(SourceEntityMappingRecord)
            .values(
                id=mapping_id,
                bookmaker_id=bookmaker_id,
                entity_type=entity_type,
                source_id=source_id,
                canonical_id=canonical_id,
                source_name=source_name,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                connector_version=None,
            )
            .on_conflict_do_nothing(
                index_elements=["bookmaker_id", "entity_type", "source_id"]
            )
            .returning(SourceEntityMappingRecord.id)
        ).scalar_one_or_none()
        return inserted is not None

    @staticmethod
    def _require_canonical(plan: DecisionPlan) -> UUID:
        if plan.canonical_id is None:
            raise RuntimeError("accepted matching decision requires a canonical UUID")
        return plan.canonical_id

    def _persist_decision(self, session: Session, decision: DecisionDraft) -> UUID:
        if decision.state is MatchState.REUSED:
            raise RuntimeError("reused mappings must not create matching decisions")
        decision_id = uuid5(_MATCHING_NAMESPACE, f"decision:{decision.decision_key}")
        session.execute(
            insert(MatchDecisionRecord)
            .values(
                id=decision_id,
                bookmaker_id=decision.bookmaker_id,
                entity_type=decision.entity_type,
                source_id=decision.source_id,
                source_fingerprint=decision.source_fingerprint,
                rule_version=decision.rule_version,
                decision_key=decision.decision_key,
                state=decision.state.value,
                canonical_id=decision.canonical_id,
                reason_code=decision.reason_code,
                best_score=decision.best_score,
                runner_up_score=decision.runner_up_score,
                evidence=decision.evidence,
                created_at=decision.created_at,
            )
            .on_conflict_do_nothing(index_elements=["decision_key"])
        )
        record = session.scalar(
            select(MatchDecisionRecord).where(
                MatchDecisionRecord.decision_key == decision.decision_key
            )
        )
        if record is None:
            raise RuntimeError("matching decision insert did not produce a persisted row")
        if record.id == decision_id:
            for candidate in decision.candidates[:5]:
                session.execute(
                    insert(MatchCandidateRecord)
                    .values(
                        decision_id=decision_id,
                        candidate_id=candidate.candidate_id,
                        rank=candidate.rank,
                        score=candidate.score,
                        disposition=candidate.disposition.value,
                        reason_codes=list(candidate.reason_codes),
                    )
                    .on_conflict_do_nothing()
                )
        return record.id

    @staticmethod
    def _insert_competition_alias(
        session: Session,
        *,
        competition_id: UUID,
        alias: str,
        provenance: str,
    ) -> None:
        if not alias:
            return
        session.execute(
            insert(CompetitionAliasRecord)
            .values(
                competition_id=competition_id,
                normalized_alias=alias,
                source=provenance,
            )
            .on_conflict_do_nothing(
                index_elements=["competition_id", "normalized_alias"]
            )
        )

    @staticmethod
    def _insert_participant_alias(
        session: Session,
        *,
        participant_id: UUID,
        alias: str,
        provenance: str,
    ) -> None:
        if not alias:
            return
        session.execute(
            insert(ParticipantAliasRecord)
            .values(
                participant_id=participant_id,
                normalized_alias=alias,
                source=provenance,
            )
            .on_conflict_do_nothing(
                index_elements=["participant_id", "normalized_alias"]
            )
        )

    @staticmethod
    def _bookmaker_provenance(bookmaker_code: str) -> str:
        return f"bookmaker:{bookmaker_code}"[:128]

    @staticmethod
    def _event_status(value: str) -> str:
        normalized = normalize_role(value)
        if normalized in {
            "scheduled",
            "suspended",
            "finished",
            "cancelled",
            "postponed",
            "unknown",
        }:
            return normalized
        return "unknown"
