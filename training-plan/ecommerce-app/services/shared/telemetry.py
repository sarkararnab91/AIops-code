"""
Shared Telemetry Module for E-Commerce Microservices
Provides Application Insights integration and distributed tracing.
"""

import os
import time
import logging
from typing import Optional, Dict, Any, Callable
from functools import wraps
from contextvars import ContextVar
import uuid

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode, SpanKind
from opentelemetry.propagate import extract, inject
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
import structlog


# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Context variable for correlation ID
correlation_id_var: ContextVar[str] = ContextVar('correlation_id', default='')

# W3C Trace Context propagator
propagator = TraceContextTextMapPropagator()


def configure_telemetry(service_name: str) -> None:
    """Configure Azure Monitor and OpenTelemetry for a service."""
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    
    if connection_string:
        configure_azure_monitor(
            connection_string=connection_string,
            service_name=service_name,
            enable_live_metrics=True,
        )
        logger.info("Azure Monitor configured", service_name=service_name)
    else:
        logger.warning(
            "APPLICATIONINSIGHTS_CONNECTION_STRING not set, telemetry disabled",
            service_name=service_name
        )
    
    # Instrument HTTP clients
    HTTPXClientInstrumentor().instrument()


def instrument_fastapi(app) -> None:
    """Instrument a FastAPI application with OpenTelemetry."""
    FastAPIInstrumentor.instrument_app(app)


def get_correlation_id() -> str:
    """Get current correlation ID from context."""
    return correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID in context."""
    correlation_id_var.set(correlation_id)


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer instance for the given name."""
    return trace.get_tracer(name)


def get_current_span() -> Optional[trace.Span]:
    """Get the current active span."""
    return trace.get_current_span()


class TracingMiddleware:
    """
    ASGI Middleware for distributed tracing in FastAPI.
    Extracts trace context from incoming requests and propagates correlation IDs.
    """
    
    def __init__(self, app, service_name: str):
        self.app = app
        self.service_name = service_name
        self.tracer = get_tracer(service_name)
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Extract headers
        headers = dict(scope.get("headers", []))
        headers = {k.decode(): v.decode() for k, v in headers.items()}
        
        # Extract trace context
        context = extract(headers)
        
        # Get or generate correlation ID
        correlation_id = headers.get(
            "x-correlation-id", 
            str(uuid.uuid4())
        )
        set_correlation_id(correlation_id)
        
        # Get request details
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")
        
        # Start span
        with self.tracer.start_as_current_span(
            f"{method} {path}",
            context=context,
            kind=SpanKind.SERVER,
            attributes={
                "http.method": method,
                "http.route": path,
                "http.scheme": scope.get("scheme", "http"),
                "service.name": self.service_name,
                "correlation_id": correlation_id,
            }
        ) as span:
            # Custom send to capture response status
            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    status_code = message.get("status", 200)
                    span.set_attribute("http.status_code", status_code)
                    
                    if status_code >= 500:
                        span.set_status(Status(StatusCode.ERROR))
                    elif status_code >= 400:
                        span.set_status(Status(StatusCode.ERROR, f"HTTP {status_code}"))
                    else:
                        span.set_status(Status(StatusCode.OK))
                    
                    # Add trace headers to response
                    headers = list(message.get("headers", []))
                    headers.append((b"x-correlation-id", correlation_id.encode()))
                    trace_id = format(span.get_span_context().trace_id, '032x')
                    headers.append((b"x-trace-id", trace_id.encode()))
                    message["headers"] = headers
                
                await send(message)
            
            await self.app(scope, receive, send_wrapper)


class TracingHTTPClient:
    """
    HTTP client wrapper that propagates trace context.
    Use this for service-to-service communication.
    """
    
    def __init__(self, base_url: str, service_name: str):
        self.base_url = base_url.rstrip('/')
        self.service_name = service_name
        self.tracer = get_tracer(service_name)
    
    async def request(
        self, 
        method: str, 
        path: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Make HTTP request with trace context propagation."""
        import httpx
        
        url = f"{self.base_url}{path}"
        
        with self.tracer.start_as_current_span(
            f"{method} {path}",
            kind=SpanKind.CLIENT,
            attributes={
                "http.method": method,
                "http.url": url,
                "peer.service": self._extract_service_name(path),
            }
        ) as span:
            # Inject trace context into headers
            headers = kwargs.pop('headers', {})
            inject(headers)
            headers['x-correlation-id'] = get_correlation_id()
            
            start_time = time.time()
            
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.request(
                        method,
                        url,
                        headers=headers,
                        **kwargs
                    )
                
                span.set_attribute("http.status_code", response.status_code)
                
                if response.status_code >= 400:
                    span.set_status(Status(StatusCode.ERROR))
                else:
                    span.set_status(Status(StatusCode.OK))
                
                return {
                    "status_code": response.status_code,
                    "data": response.json() if response.content else None,
                    "headers": dict(response.headers)
                }
                
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            
            finally:
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("http.duration_ms", duration_ms)
    
    async def get(self, path: str, **kwargs) -> Dict[str, Any]:
        return await self.request("GET", path, **kwargs)
    
    async def post(self, path: str, **kwargs) -> Dict[str, Any]:
        return await self.request("POST", path, **kwargs)
    
    async def put(self, path: str, **kwargs) -> Dict[str, Any]:
        return await self.request("PUT", path, **kwargs)
    
    async def delete(self, path: str, **kwargs) -> Dict[str, Any]:
        return await self.request("DELETE", path, **kwargs)
    
    def _extract_service_name(self, path: str) -> str:
        """Extract target service name from path."""
        parts = path.split('/')
        service_map = {
            'products': 'catalog-service',
            'catalog': 'catalog-service',
            'cart': 'cart-service',
            'orders': 'order-service',
            'payments': 'payment-service',
            'users': 'user-service',
            'inventory': 'inventory-service',
            'notifications': 'notification-service',
        }
        for part in parts:
            if part in service_map:
                return service_map[part]
        return 'unknown-service'


def trace_operation(
    name: str,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Optional[Dict[str, Any]] = None
):
    """Decorator to create a traced operation."""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracer(__name__)
            
            span_attributes = {"correlation_id": get_correlation_id()}
            if attributes:
                span_attributes.update(attributes)
            
            with tracer.start_as_current_span(
                name,
                kind=kind,
                attributes=span_attributes
            ) as span:
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = get_tracer(__name__)
            
            span_attributes = {"correlation_id": get_correlation_id()}
            if attributes:
                span_attributes.update(attributes)
            
            with tracer.start_as_current_span(
                name,
                kind=kind,
                attributes=span_attributes
            ) as span:
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def add_span_attribute(key: str, value: Any) -> None:
    """Add an attribute to the current span."""
    span = get_current_span()
    if span:
        span.set_attribute(key, value)


def add_span_event(name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
    """Add an event to the current span."""
    span = get_current_span()
    if span:
        span.add_event(name, attributes=attributes or {})


def track_custom_event(
    name: str,
    properties: Optional[Dict[str, Any]] = None,
    measurements: Optional[Dict[str, float]] = None
) -> None:
    """Track a custom event for Application Insights."""
    span = get_current_span()
    if span:
        event_attrs = {
            "event.name": name,
            "correlation_id": get_correlation_id()
        }
        if properties:
            for k, v in properties.items():
                event_attrs[f"custom.{k}"] = str(v)
        if measurements:
            for k, v in measurements.items():
                event_attrs[f"metric.{k}"] = v
        
        span.add_event(name, attributes=event_attrs)
    
    # Also log for structured logging
    logger.info(
        "custom_event",
        event_name=name,
        properties=properties,
        measurements=measurements,
        correlation_id=get_correlation_id()
    )


def track_dependency(
    name: str,
    dependency_type: str,
    target: str,
    duration_ms: float,
    success: bool,
    data: Optional[str] = None
) -> None:
    """Track a dependency call for Application Insights."""
    tracer = get_tracer(__name__)
    
    with tracer.start_as_current_span(
        name,
        kind=SpanKind.CLIENT,
        attributes={
            "dependency.type": dependency_type,
            "dependency.target": target,
            "dependency.data": data or "",
            "dependency.duration_ms": duration_ms,
            "dependency.success": success,
            "correlation_id": get_correlation_id()
        }
    ) as span:
        if success:
            span.set_status(Status(StatusCode.OK))
        else:
            span.set_status(Status(StatusCode.ERROR))


class TelemetryLogger:
    """
    Structured logger with telemetry integration.
    Automatically includes correlation ID and service context.
    """
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.logger = structlog.get_logger()
    
    def _add_context(self, **kwargs) -> Dict[str, Any]:
        return {
            "service_name": self.service_name,
            "correlation_id": get_correlation_id(),
            **kwargs
        }
    
    def info(self, message: str, **kwargs) -> None:
        self.logger.info(message, **self._add_context(**kwargs))
    
    def warning(self, message: str, **kwargs) -> None:
        self.logger.warning(message, **self._add_context(**kwargs))
    
    def error(self, message: str, **kwargs) -> None:
        self.logger.error(message, **self._add_context(**kwargs))
        # Also record to span
        span = get_current_span()
        if span:
            span.add_event("error", attributes={"message": message, **kwargs})
    
    def debug(self, message: str, **kwargs) -> None:
        self.logger.debug(message, **self._add_context(**kwargs))
    
    def exception(self, message: str, **kwargs) -> None:
        self.logger.exception(message, **self._add_context(**kwargs))
        # Also record exception to span
        span = get_current_span()
        if span:
            import sys
            exc_info = sys.exc_info()
            if exc_info[1]:
                span.record_exception(exc_info[1])
