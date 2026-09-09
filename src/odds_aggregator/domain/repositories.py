from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .models import OddsQuote, SourceEntityMapping, SourceEntityType


class SourceMappingRepository(Protocol):
    def get(
        self,
        *,
        bookmaker_id: UUID,
        entity_type: SourceEntityType,
        source_id: str,
    ) -> SourceEntityMapping | None: ...

    def upsert(self, mapping: SourceEntityMapping) -> SourceEntityMapping: ...


class HistoricalOddsRepository(Protocol):
    def append(self, quote: OddsQuote) -> bool:
        """Persist quote if unseen; return True when inserted, False on replay."""
        ...
