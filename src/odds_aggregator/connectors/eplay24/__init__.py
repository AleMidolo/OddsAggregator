"""Eplay24 connector using the permitted OddsPapi API."""

from .connector import OddsPapiClient
from .freshness import Eplay24OddsPapiConnector

__all__ = ["Eplay24OddsPapiConnector", "OddsPapiClient"]
