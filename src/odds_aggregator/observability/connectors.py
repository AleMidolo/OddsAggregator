"""Connector operation metrics and run outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, Protocol, TypeVar

T = TypeVar("T")


class ConnectorRunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    THROTTLED = "throttled"
    CIRCUIT_OPEN = "circuit_open"


@dataclass(frozen=True, slots=True)
class ConnectorOperationMetric:
    bookmaker_code: str
    operation: str
    attempt: int
    latency_seconds: float
    rate_limit_wait_seconds: float
    retry_scheduled: bool
    error_type: str | None = None


class ConnectorMetricsSink(Protocol):
    def record(self, metric: ConnectorOperationMetric) -> None: ...


@dataclass(slots=True)
class InMemoryConnectorMetrics:
    metrics: list[ConnectorOperationMetric] = field(default_factory=list)

    def record(self, metric: ConnectorOperationMetric) -> None:
        self.metrics.append(metric)


@dataclass(frozen=True, slots=True)
class ConnectorRunOutcome(Generic[T]):
    bookmaker_code: str
    operation: str
    status: ConnectorRunStatus
    attempts: int
    value: T | None = None
    error: BaseException | None = None
