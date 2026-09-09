"""Per-bookmaker timeout, rate-limit, retry, concurrency, and circuit controls."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from odds_aggregator.connectors.errors import (
    ConnectorCircuitOpenError,
    ConnectorError,
    ConnectorRateLimitedError,
    ConnectorTimeoutError,
    ConnectorUnavailableError,
)
from odds_aggregator.observability import (
    ConnectorMetricsSink,
    ConnectorOperationMetric,
    ConnectorRunOutcome,
    ConnectorRunStatus,
)

T = TypeVar("T")
Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]
RandomSource = Callable[[], float]


@dataclass(frozen=True, slots=True)
class ConnectorResiliencePolicy:
    timeout_seconds: float = 10.0
    job_timeout_seconds: float = 30.0
    max_concurrency: int = 4
    rate_limit_per_second: float = 10.0
    rate_limit_burst: int = 1
    max_attempts: int = 3
    base_backoff_seconds: float = 0.25
    max_backoff_seconds: float = 5.0
    jitter_ratio: float = 0.2
    circuit_failure_threshold: int = 5
    circuit_reset_seconds: float = 30.0

    def __post_init__(self) -> None:
        numeric_positive = {
            "timeout_seconds": self.timeout_seconds,
            "job_timeout_seconds": self.job_timeout_seconds,
            "rate_limit_per_second": self.rate_limit_per_second,
            "max_backoff_seconds": self.max_backoff_seconds,
            "circuit_reset_seconds": self.circuit_reset_seconds,
        }
        if any(value <= 0 for value in numeric_positive.values()):
            raise ValueError("timeout, rate, backoff maximum, and reset values must be positive")
        if self.max_concurrency < 1 or self.rate_limit_burst < 1 or self.max_attempts < 1:
            raise ValueError("concurrency, burst, and max_attempts must be at least 1")
        if self.base_backoff_seconds < 0:
            raise ValueError("base_backoff_seconds cannot be negative")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")
        if self.circuit_failure_threshold < 1:
            raise ValueError("circuit_failure_threshold must be at least 1")


class AsyncTokenBucket:
    """Small async token bucket suitable for independently scoped provider limits."""

    def __init__(
        self,
        rate_per_second: float,
        burst: int,
        *,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if rate_per_second <= 0 or burst < 1:
            raise ValueError("rate_per_second must be positive and burst must be at least 1")
        self._rate = rate_per_second
        self._capacity = float(burst)
        self._tokens = float(burst)
        self._clock = clock
        self._sleep = sleep
        self._last_refill = clock()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        total_wait = 0.0
        while True:
            async with self._lock:
                now = self._clock()
                elapsed = max(0.0, now - self._last_refill)
                if elapsed:
                    self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                    self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return total_wait
                delay = (1.0 - self._tokens) / self._rate
            await self._sleep(delay)
            total_wait += delay


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int,
        reset_seconds: float,
        *,
        clock: Clock = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._reset_seconds = reset_seconds
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at: float | None = None
        self._half_open_in_flight = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def before_call(self) -> None:
        async with self._lock:
            if self._state is CircuitState.CLOSED:
                return
            if self._state is CircuitState.OPEN:
                assert self._opened_at is not None
                if self._clock() - self._opened_at < self._reset_seconds:
                    raise ConnectorCircuitOpenError("connector circuit is open")
                self._state = CircuitState.HALF_OPEN
                self._half_open_in_flight = False
            if self._half_open_in_flight:
                raise ConnectorCircuitOpenError("connector circuit half-open probe already running")
            self._half_open_in_flight = True

    async def record_success(self) -> None:
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failures = 0
            self._opened_at = None
            self._half_open_in_flight = False

    async def record_failure(self) -> None:
        async with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._open()
                return
            self._failures += 1
            if self._failures >= self._failure_threshold:
                self._open()

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
        self._half_open_in_flight = False


@dataclass(slots=True)
class _BookmakerControls:
    policy: ConnectorResiliencePolicy
    semaphore: asyncio.Semaphore
    limiter: AsyncTokenBucket
    circuit: CircuitBreaker


class ConnectorResilienceRegistry:
    """Build and retain independent controls for each bookmaker code."""

    def __init__(
        self,
        policies: Mapping[str, ConnectorResiliencePolicy],
        *,
        default_policy: ConnectorResiliencePolicy | None = None,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._policies = dict(policies)
        self._default_policy = default_policy or ConnectorResiliencePolicy()
        self._clock = clock
        self._sleep = sleep
        self._controls: dict[str, _BookmakerControls] = {}

    def controls_for(self, bookmaker_code: str) -> _BookmakerControls:
        controls = self._controls.get(bookmaker_code)
        if controls is not None:
            return controls
        policy = self._policies.get(bookmaker_code, self._default_policy)
        controls = _BookmakerControls(
            policy=policy,
            semaphore=asyncio.Semaphore(policy.max_concurrency),
            limiter=AsyncTokenBucket(
                policy.rate_limit_per_second,
                policy.rate_limit_burst,
                clock=self._clock,
                sleep=self._sleep,
            ),
            circuit=CircuitBreaker(
                policy.circuit_failure_threshold,
                policy.circuit_reset_seconds,
                clock=self._clock,
            ),
        )
        self._controls[bookmaker_code] = controls
        return controls


class _NullMetrics:
    def record(self, metric: ConnectorOperationMetric) -> None:
        del metric


class ConnectorOperationExecutor:
    def __init__(
        self,
        registry: ConnectorResilienceRegistry,
        *,
        metrics: ConnectorMetricsSink | None = None,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        random_source: RandomSource = random.random,
    ) -> None:
        self._registry = registry
        self._metrics = metrics or _NullMetrics()
        self._clock = clock
        self._sleep = sleep
        self._random_source = random_source

    async def run(
        self,
        bookmaker_code: str,
        operation_name: str,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        controls = self._registry.controls_for(bookmaker_code)
        try:
            async with asyncio.timeout(controls.policy.job_timeout_seconds):
                return await self._run_attempts(bookmaker_code, operation_name, operation, controls)
        except TimeoutError as exc:
            raise ConnectorTimeoutError("connector job deadline exceeded") from exc

    async def _run_attempts(
        self,
        bookmaker_code: str,
        operation_name: str,
        operation: Callable[[], Awaitable[T]],
        controls: _BookmakerControls,
    ) -> T:
        policy = controls.policy
        for attempt in range(1, policy.max_attempts + 1):
            await controls.circuit.before_call()
            rate_wait = await controls.limiter.acquire()
            started = self._clock()
            try:
                async with controls.semaphore:
                    try:
                        async with asyncio.timeout(policy.timeout_seconds):
                            value = await operation()
                    except TimeoutError as exc:
                        raise ConnectorTimeoutError("connector operation timed out") from exc
            except ConnectorError as error:
                latency = max(0.0, self._clock() - started)
                retry = error.retryable and attempt < policy.max_attempts
                self._metrics.record(
                    ConnectorOperationMetric(
                        bookmaker_code=bookmaker_code,
                        operation=operation_name,
                        attempt=attempt,
                        latency_seconds=latency,
                        rate_limit_wait_seconds=rate_wait,
                        retry_scheduled=retry,
                        error_type=type(error).__name__,
                    )
                )
                if isinstance(error, (ConnectorTimeoutError, ConnectorUnavailableError)):
                    await controls.circuit.record_failure()
                if not retry:
                    raise
                await self._sleep(self._retry_delay(policy, error, attempt))
            else:
                latency = max(0.0, self._clock() - started)
                await controls.circuit.record_success()
                self._metrics.record(
                    ConnectorOperationMetric(
                        bookmaker_code=bookmaker_code,
                        operation=operation_name,
                        attempt=attempt,
                        latency_seconds=latency,
                        rate_limit_wait_seconds=rate_wait,
                        retry_scheduled=False,
                    )
                )
                return value
        raise RuntimeError("unreachable retry loop")

    def _retry_delay(
        self,
        policy: ConnectorResiliencePolicy,
        error: ConnectorError,
        attempt: int,
    ) -> float:
        if isinstance(error, ConnectorRateLimitedError) and error.retry_after_seconds is not None:
            return max(0.0, error.retry_after_seconds)
        exponential = min(
            policy.max_backoff_seconds,
            policy.base_backoff_seconds * (2 ** (attempt - 1)),
        )
        if exponential == 0 or policy.jitter_ratio == 0:
            return exponential
        jitter = (self._random_source() * 2.0 - 1.0) * policy.jitter_ratio
        return max(0.0, exponential * (1.0 + jitter))


async def run_isolated_operations(
    executor: ConnectorOperationExecutor,
    operation_name: str,
    operations: Mapping[str, Callable[[], Awaitable[T]]],
) -> dict[str, ConnectorRunOutcome[T]]:
    async def run_one(
        bookmaker_code: str,
        operation: Callable[[], Awaitable[T]],
    ) -> ConnectorRunOutcome[T]:
        attempt_count = 0

        async def counted_operation() -> T:
            nonlocal attempt_count
            attempt_count += 1
            return await operation()

        try:
            value = await executor.run(bookmaker_code, operation_name, counted_operation)
        except ConnectorRateLimitedError as error:
            return ConnectorRunOutcome(
                bookmaker_code=bookmaker_code,
                operation=operation_name,
                status=ConnectorRunStatus.THROTTLED,
                attempts=attempt_count,
                error=error,
            )
        except ConnectorCircuitOpenError as error:
            return ConnectorRunOutcome(
                bookmaker_code=bookmaker_code,
                operation=operation_name,
                status=ConnectorRunStatus.CIRCUIT_OPEN,
                attempts=attempt_count,
                error=error,
            )
        except Exception as error:
            return ConnectorRunOutcome(
                bookmaker_code=bookmaker_code,
                operation=operation_name,
                status=ConnectorRunStatus.FAILED,
                attempts=attempt_count,
                error=error,
            )
        return ConnectorRunOutcome(
            bookmaker_code=bookmaker_code,
            operation=operation_name,
            status=ConnectorRunStatus.SUCCEEDED,
            attempts=attempt_count,
            value=value,
        )

    results = await asyncio.gather(
        *(run_one(code, operation) for code, operation in operations.items())
    )
    return {result.bookmaker_code: result for result in results}
