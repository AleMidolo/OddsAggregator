from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from .matching_write import MatchingWriteMixin


class SQLAlchemyMatchingStore(MatchingWriteMixin):
    """PostgreSQL-backed prematch matching store with bounded transactions."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
