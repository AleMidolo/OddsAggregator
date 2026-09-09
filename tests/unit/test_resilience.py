from __future__ import annotations

import asyncio

import pytest

from odds_aggregator.connectors import (
    ConnectorAuthenticationError,
    ConnectorCircuitOpenError,
    ConnectorRateLimitedError,
    ConnectorTimeoutError,
    ConnectorUnavailableError,
    SourceSport,
)
from odds_aggregator.connectors.fake import FakeBookmakerConnector
from odds_aggregator.ingestion import (
    AsyncTokenBucket,
    CircuitState,
    ConnectorOperationExecutor,
    ConnectorResiliencePolicy,
    ConnectorResilienceRegistry,
    run_isolated_operations,
)
from odds_aggregator.observability import ConnectorRunStatus, InMemoryConnectorMetrics


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.value

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds
        await asyncio.sleep(0)


def build_executor(
    policy: ConnectorResiliencePolicy,
    *,
    clock: FakeClock | None = None,
) -> tuple[ConnectorOperationExecutor, InMemoryConnectorMetrics, FakeClock]:
    fake_clock = clock or FakeClock()
    metrics = InMemoryConnectorMetrics()
    registry = ConnectorResilienceRegistry(
        {"book-a": policy, "book-b": policy},
        clock=fake_clock,
        sleep=fake_clock.sleep,
    )
    executor = ConnectorOperationExecutor(
        registry,
        metrics=metrics,
        clock=fake_clock,
        sleep=fake_clock.sleep,
        random_source=lambda: 0.5,
    )
    return executor, metrics, fake_clock


@pytest.mark.asyncio
async def test_transient_failures_retry_with_exponential_backoff() -> None:
    policy = ConnectorResiliencePolicy(
        max_attempts=3,
        base_backoff_seconds=0.5,
        jitter_ratio=0,
        rate_limit_per_second=1000,
        rate_limit_burst=10,
        circuit_failure_threshold=5,
    )
    executor, metrics, clock = build_executor(policy)
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectorUnavailableError("temporary")
        return "ok"

    assert await executor.run("book-a", "events", operation) == "ok"
    assert attempts == 3
    assert clock.sleeps[:2] == [0.5, 1.0]
    assert [metric.retry_scheduled for metric in metrics.metrics] == [True, True, False]


@pytest.mark.asyncio
async def test_retry_after_precedes_exponential_backoff() -> None:
    policy = ConnectorResiliencePolicy(
        max_attempts=2,
        base_backoff_seconds=9,
        jitter_ratio=0,
        rate_limit_per_second=1000,
        rate_limit_burst=10,
    )
    executor, _, clock = build_executor(policy)
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectorRateLimitedError("limited", retry_after_seconds=2.5)
        return "ok"

    assert await executor.run("book-a", "markets", operation) == "ok"
    assert clock.sleeps[0] == 2.5


@pytest.mark.asyncio
async def test_permanent_failure_is_not_retried() -> None:
    policy = ConnectorResiliencePolicy(
        max_attempts=4,
        rate_limit_per_second=1000,
        rate_limit_burst=10,
    )
    executor, _, _ = build_executor(policy)
    attempts = 0

    async def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise ConnectorAuthenticationError("invalid credentials")

    with pytest.raises(ConnectorAuthenticationError):
        await executor.run("book-a", "sports", operation)
    assert attempts == 1


@pytest.mark.asyncio
async def test_timeout_is_translated_and_bounded() -> None:
    policy = ConnectorResiliencePolicy(
        timeout_seconds=0.01,
        job_timeout_seconds=1,
        max_attempts=1,
        rate_limit_per_second=1000,
        rate_limit_burst=10,
    )
    executor, _, _ = build_executor(policy)

    async def slow_operation() -> None:
        await asyncio.sleep(0.1)

    with pytest.raises(ConnectorTimeoutError):
        await executor.run("book-a", "events", slow_operation)


@pytest.mark.asyncio
async def test_external_cancellation_propagates() -> None:
    policy = ConnectorResiliencePolicy(
        timeout_seconds=10,
        job_timeout_seconds=20,
        rate_limit_per_second=1000,
        rate_limit_burst=10,
    )
    executor, _, _ = build_executor(policy)
    started = asyncio.Event()

    async def operation() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(executor.run("book-a", "events", operation))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_circuit_opens_only_for_the_failing_bookmaker() -> None:
    policy = ConnectorResiliencePolicy(
        max_attempts=3,
        base_backoff_seconds=0,
        rate_limit_per_second=1000,
        rate_limit_burst=10,
        circuit_failure_threshold=2,
        circuit_reset_seconds=60,
    )
    executor, _, _ = build_executor(policy)

    async def unavailable() -> str:
        raise ConnectorUnavailableError("down")

    with pytest.raises(ConnectorCircuitOpenError):
        await executor.run("book-a", "events", unavailable)

    assert executor._registry.controls_for("book-a").circuit.state is CircuitState.OPEN
    assert executor._registry.controls_for("book-b").circuit.state is CircuitState.CLOSED

    async def healthy() -> str:
        return "ok"

    assert await executor.run("book-b", "events", healthy) == "ok"


@pytest.mark.asyncio
async def test_one_failing_connector_does_not_stop_another() -> None:
    policy = ConnectorResiliencePolicy(
        max_attempts=1,
        rate_limit_per_second=1000,
        rate_limit_burst=10,
    )
    executor, _, _ = build_executor(policy)
    failed_connector = FakeBookmakerConnector(
        bookmaker_code="book-a",
        failure_plan={"list_sports": (ConnectorAuthenticationError("bad config"),)},
    )
    healthy_connector = FakeBookmakerConnector(
        bookmaker_code="book-b",
        sports=(SourceSport(source_id="football", name="Football"),),
    )

    outcomes = await run_isolated_operations(
        executor,
        "list_sports",
        {
            "book-a": failed_connector.list_sports,
            "book-b": healthy_connector.list_sports,
        },
    )

    assert outcomes["book-a"].status is ConnectorRunStatus.FAILED
    assert outcomes["book-a"].attempts == 1
    assert outcomes["book-b"].status is ConnectorRunStatus.SUCCEEDED
    assert outcomes["book-b"].value == [SourceSport(source_id="football", name="Football")]


@pytest.mark.asyncio
async def test_concurrency_limit_is_scoped_per_bookmaker() -> None:
    policy = ConnectorResiliencePolicy(
        max_concurrency=1,
        max_attempts=1,
        rate_limit_per_second=1000,
        rate_limit_burst=10,
    )
    executor, _, _ = build_executor(policy)
    release_a = asyncio.Event()
    a_entered = 0
    b_entered = asyncio.Event()

    async def book_a_operation() -> str:
        nonlocal a_entered
        a_entered += 1
        await release_a.wait()
        return "a"

    async def book_b_operation() -> str:
        b_entered.set()
        return "b"

    first_a = asyncio.create_task(executor.run("book-a", "events", book_a_operation))
    while a_entered == 0:
        await asyncio.sleep(0)
    second_a = asyncio.create_task(executor.run("book-a", "events", book_a_operation))
    book_b = asyncio.create_task(executor.run("book-b", "events", book_b_operation))

    await b_entered.wait()
    await asyncio.sleep(0)
    assert a_entered == 1

    release_a.set()
    assert await first_a == "a"
    assert await second_a == "a"
    assert await book_b == "b"


@pytest.mark.asyncio
async def test_rate_limiter_wait_is_independent_per_bookmaker() -> None:
    clock = FakeClock()
    limiter_a = AsyncTokenBucket(2.0, 1, clock=clock, sleep=clock.sleep)
    limiter_b = AsyncTokenBucket(2.0, 1, clock=clock, sleep=clock.sleep)

    assert await limiter_a.acquire() == 0
    assert await limiter_b.acquire() == 0
    assert await limiter_a.acquire() == 0.5
