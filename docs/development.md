# Local backend development

## Requirements

- Python 3.12+
- PostgreSQL 15+

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

On Windows PowerShell, activate with `.venv\\Scripts\\Activate.ps1`.

## Database

Create a local PostgreSQL database and set an SQLAlchemy URL:

```bash
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/odds_aggregator'
alembic upgrade head
```

`DATABASE_URL` is consumed by Alembic. PostgreSQL is authoritative; Redis is not required for this foundation.

## Tests

Unit tests require no database:

```bash
pytest tests/unit
```

Persistence integration tests intentionally require PostgreSQL and are skipped when no test database is configured:

```bash
export TEST_DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/odds_aggregator_test'
pytest tests/integration
```

The integration suite migrates the configured test database down to `base` and back to `head`; use a disposable database only.

Run all local quality checks with:

```bash
ruff check .
mypy src
pytest
```

No test path performs live bookmaker/provider network calls.

## Transaction boundary

Persistence repositories accept an existing SQLAlchemy `Session`; application/ingestion code owns the transaction boundary. Connector network I/O must happen before opening or after closing a database transaction, never while one is held open.
