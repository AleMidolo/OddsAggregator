"""Bet365 connector backed by the permitted Sportradar Odds Comparison API."""

from .connector import Bet365SportradarConnector, SportradarPrematchClient

__all__ = ["Bet365SportradarConnector", "SportradarPrematchClient"]
