"""SQLAlchemy persistence adapters."""

from .base import Base
from .database import create_database_engine, create_session_factory
from .ingestion import SQLAlchemyIngestionStore
from .matching import SQLAlchemyMatchingStore
from .matching_models import MatchCandidateRecord, MatchDecisionRecord
from .repositories import SQLAlchemyHistoricalOddsRepository, SQLAlchemySourceMappingRepository

__all__ = [
    "Base",
    "MatchCandidateRecord",
    "MatchDecisionRecord",
    "SQLAlchemyHistoricalOddsRepository",
    "SQLAlchemyIngestionStore",
    "SQLAlchemyMatchingStore",
    "SQLAlchemySourceMappingRepository",
    "create_database_engine",
    "create_session_factory",
]
