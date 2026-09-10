from odds_aggregator.persistence.models import OddsQuoteRecord


def test_unavailable_odds_column_is_nullable_in_orm_metadata() -> None:
    """ORM metadata must match migration 0002 for unavailable observations."""
    assert OddsQuoteRecord.__table__.c.decimal_odds.nullable is True
