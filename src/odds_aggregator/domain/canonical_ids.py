from __future__ import annotations

from uuid import UUID, uuid5

_CANONICAL_NAMESPACE = UUID("120ddf53-4180-4b56-a91e-66bd57ac1b78")


def canonical_entity_id(bookmaker_id: UUID, entity_type: str, source_id: str) -> UUID:
    """Return the canonical UUID used by ingestion for first-source entity creation."""
    return uuid5(_CANONICAL_NAMESPACE, f"{bookmaker_id}:{entity_type}:{source_id}")
