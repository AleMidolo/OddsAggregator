"""Bet365 connector backed by the permitted Sportradar Odds Comparison API."""

from .connector import SportradarPrematchClient
from .semantic import Bet365SportradarConnector

__all__ = ["Bet365SportradarConnector", "SportradarPrematchClient"]
