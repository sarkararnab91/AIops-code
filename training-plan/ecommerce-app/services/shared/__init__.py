"""Shared module for E-Commerce microservices."""

from .telemetry import (
    configure_telemetry,
    instrument_fastapi,
    TracingMiddleware,
    TracingHTTPClient,
    trace_operation,
    add_span_attribute,
    add_span_event,
    track_custom_event,
    track_dependency,
    get_correlation_id,
    set_correlation_id,
    TelemetryLogger,
)

from .database import (
    CosmosDBClient,
    RedisClient,
    get_cosmos_client,
    get_redis_client,
    database_lifespan,
)

__all__ = [
    # Telemetry
    "configure_telemetry",
    "instrument_fastapi",
    "TracingMiddleware",
    "TracingHTTPClient",
    "trace_operation",
    "add_span_attribute",
    "add_span_event",
    "track_custom_event",
    "track_dependency",
    "get_correlation_id",
    "set_correlation_id",
    "TelemetryLogger",
    # Database
    "CosmosDBClient",
    "RedisClient",
    "get_cosmos_client",
    "get_redis_client",
    "database_lifespan",
]
