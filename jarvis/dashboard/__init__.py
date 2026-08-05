"""Jarvis Dashboard and observability surface."""

from jarvis.dashboard.backend import DashboardBackend
from jarvis.dashboard.observability import DashboardEventBridge, ObservabilityHub
from jarvis.dashboard.projection import DashboardProjectionEngine, SafeDashboardProjectionHandler
from jarvis.dashboard.projection_models import (
    DashboardProjectionSnapshot,
    NodeView,
    ProjectionHealth,
    ProjectionHealthStatus,
    ProjectionVersion,
    RuntimeSessionView,
    TimelineView,
)
from jarvis.dashboard.projection_repository import (
    DashboardProjectionRepository,
    InMemoryDashboardProjectionRepository,
    SQLiteDashboardProjectionRepository,
)

__all__ = [
    "DashboardBackend", "DashboardEventBridge", "ObservabilityHub",
    "DashboardProjectionEngine", "SafeDashboardProjectionHandler",
    "DashboardProjectionSnapshot", "NodeView", "ProjectionHealth",
    "ProjectionHealthStatus", "ProjectionVersion", "RuntimeSessionView",
    "TimelineView", "DashboardProjectionRepository",
    "InMemoryDashboardProjectionRepository", "SQLiteDashboardProjectionRepository",
]
