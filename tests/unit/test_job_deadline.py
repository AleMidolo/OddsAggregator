from __future__ import annotations

import asyncio

import pytest

from odds_aggregator.connectors import ConnectorTimeoutError
from odds_aggregator.ingestion import (
    ConnectorOperationExecutor,
    ConnectorResiliencePolicy,
    ConnectorResilienceRegistry,
)


@pytest.mark.asyncio
async def test_overall_job_deadline_preempts_longer_operation_timeout() -> None:
    policy = ConnectorResiliencePolicy(
        timeout_seconds=1.0,
        job_timeout_seconds=0.02,
        max_attempts=1,
        rate_limit_per_second=1000,
        rate_limit_burst=10,
    )
    executor = ConnectorOperationExecutor(
        ConnectorResilienceRegistry({"book-a": policy})
    )

    async def never_completes() -> None:
        await asyncio.Event().wait()

    with pytest.raises(ConnectorTimeoutError, match="job deadline exceeded"):
        await executor.run("book-a", "events", never_completes)
