"""Application Insights telemetry configuration."""

import os
import logging
from typing import Optional
from functools import wraps
import time
import asyncio

# Check if opentelemetry is installed
try:
    from azure.monitor.opentelemetry import configure_azure_monitor
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    HAS_OPENTELEMETRY = True
except ImportError:
    HAS_OPENTELEMETRY = False

import structlog

logger = structlog.get_logger()

def configure_telemetry(
    service_name: str,
    connection_string: Optional[str] = None
) -> None:
    """Configure Application Insights with OpenTelemetry."""
    if not HAS_OPENTELEMETRY:
        logger.warning("opentelemetry_not_installed")
        return

    conn_str = connection_string or os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    
    if not conn_str:
        logger.warning("Application Insights not configured - no connection string")
        return
    
    # Configure Azure Monitor
    try:
        configure_azure_monitor(
            connection_string=conn_str,
            service_name=service_name,
            enable_live_metrics=True,
        )
        
        # Auto-instrument common libraries
        RequestsInstrumentor().instrument()
        
        try:
            RedisInstrumentor().instrument()
        except:
            pass  # Redis not available
        
        logger.info("telemetry_configured", service=service_name)
    except Exception as e:
        logger.error("telemetry_configuration_failed", error=str(e))


def instrument_fastapi(app):
    """Instrument FastAPI application."""
    if HAS_OPENTELEMETRY:
        FastAPIInstrumentor.instrument_app(app)


def get_tracer(name: str = __name__):
    """Get OpenTelemetry tracer."""
    if HAS_OPENTELEMETRY:
        return trace.get_tracer(name)
    return None


class TelemetryMiddleware:
    """Custom telemetry middleware for FastAPI."""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.tracer = get_tracer(service_name)
    
    async def __call__(self, request, call_next):
        # Extract correlation ID from headers
        correlation_id = request.headers.get("X-Correlation-ID", "")
        
        if not self.tracer:
            return await call_next(request)

        with self.tracer.start_as_current_span(
            f"{request.method} {request.url.path}",
            attributes={
                "http.method": request.method,
                "http.url": str(request.url),
                "http.route": request.url.path,
                "service.name": self.service_name,
                "correlation.id": correlation_id,
            }
        ) as span:
            start_time = time.time()
            
            try:
                response = await call_next(request)
                
                # Add response attributes
                span.set_attribute("http.status_code", response.status_code)
                
                if response.status_code >= 400:
                    span.set_status(Status(StatusCode.ERROR))
                else:
                    span.set_status(Status(StatusCode.OK))
                
                return response
                
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            
            finally:
                duration = time.time() - start_time
                span.set_attribute("http.duration_ms", duration * 1000)


def track_dependency(name: str, dependency_type: str = "Custom"):
    """Decorator to track custom dependencies."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracer()
            if not tracer:
                return await func(*args, **kwargs)

            with tracer.start_as_current_span(
                name,
                attributes={
                    "dependency.type": dependency_type,
                    "dependency.name": name,
                }
            ) as span:
                start = time.time()
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
                finally:
                    span.set_attribute("duration_ms", (time.time() - start) * 1000)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = get_tracer()
            if not tracer:
                return func(*args, **kwargs)

            with tracer.start_as_current_span(
                name,
                attributes={
                    "dependency.type": dependency_type,
                    "dependency.name": name,
                }
            ) as span:
                start = time.time()
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
                finally:
                    span.set_attribute("duration_ms", (time.time() - start) * 1000)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


class MetricsTracker:
    """Track custom metrics."""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.tracer = get_tracer(service_name)
    
    def track_event(self, name: str, properties: dict = None):
        """Track a custom event."""
        if self.tracer:
            span = trace.get_current_span()
            if span:
                span.add_event(name, attributes=properties or {})
        
        logger.info("custom_event", event=name, properties=properties)
    
    def track_metric(self, name: str, value: float, properties: dict = None):
        """Track a custom metric."""
        if self.tracer:
            span = trace.get_current_span()
            if span:
                span.set_attribute(f"metric.{name}", value)
                if properties:
                    for k, v in properties.items():
                        span.set_attribute(f"metric.{name}.{k}", v)
        
        logger.info("custom_metric", metric=name, value=value, properties=properties)
