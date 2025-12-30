# Session 7: Application Insights Deep Dive

## 📋 Session Details
- **Duration**: 1 hour
- **Week**: 2, Day 2 (Tuesday)
- **Prerequisites**: Sessions 1-6 completed
- **Deliverable**: Full telemetry instrumentation across all services

---

## 🎯 Learning Objectives

By the end of this session, you will:
1. Configure Application Insights for all microservices
2. Implement custom metrics and events
3. Set up dependency tracking for external calls
4. Understand the Application Map

---

## 📚 Concepts

### Application Insights Telemetry Types

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    APPLICATION INSIGHTS TELEMETRY                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   REQUEST                 DEPENDENCY              EXCEPTION                  │
│   ┌──────────┐           ┌──────────┐           ┌──────────┐               │
│   │ Incoming │           │ Outgoing │           │  Errors  │               │
│   │ HTTP     │           │ HTTP,DB, │           │  Stack   │               │
│   │ Requests │           │ Cache    │           │  Traces  │               │
│   └──────────┘           └──────────┘           └──────────┘               │
│                                                                              │
│   TRACE                   EVENT                  METRIC                     │
│   ┌──────────┐           ┌──────────┐           ┌──────────┐               │
│   │  Log     │           │ Business │           │ Custom   │               │
│   │ Messages │           │  Events  │           │ Metrics  │               │
│   └──────────┘           └──────────┘           └──────────┘               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Correlation and Distributed Tracing

```
   Frontend Request
        │
        │ operation_id: abc123
        ▼
   ┌─────────────┐
   │   Ingress   │
   └──────┬──────┘
          │ operation_id: abc123
    ┌─────┴─────┬──────────────┐
    ▼           ▼              ▼
┌────────┐  ┌────────┐    ┌────────┐
│Catalog │  │ Cart   │    │ Order  │
│Service │  │Service │    │Service │
└───┬────┘  └────────┘    └───┬────┘
    │                         │
    │ operation_id: abc123    │ operation_id: abc123
    ▼                         ▼
┌────────┐               ┌────────┐
│CosmosDB│               │Service │
│        │               │  Bus   │
└────────┘               └────────┘

All telemetry correlated by operation_id!
```

---

## 🛠️ Hands-On Exercise

### Step 1: Create Telemetry Module

Create `ecommerce-app/shared/telemetry.py`:

```python
"""Application Insights telemetry configuration."""

import os
import logging
from typing import Optional
from functools import wraps
import time

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
import structlog

logger = structlog.get_logger()


def configure_telemetry(
    service_name: str,
    connection_string: Optional[str] = None
) -> None:
    """Configure Application Insights with OpenTelemetry."""
    
    conn_str = connection_string or os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    
    if not conn_str:
        logger.warning("Application Insights not configured - no connection string")
        return
    
    # Configure Azure Monitor
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


def instrument_fastapi(app):
    """Instrument FastAPI application."""
    FastAPIInstrumentor.instrument_app(app)


def get_tracer(name: str = __name__):
    """Get OpenTelemetry tracer."""
    return trace.get_tracer(name)


class TelemetryMiddleware:
    """Custom telemetry middleware for FastAPI."""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.tracer = get_tracer(service_name)
    
    async def __call__(self, request, call_next):
        # Extract correlation ID from headers
        correlation_id = request.headers.get("X-Correlation-ID", "")
        
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
        span = trace.get_current_span()
        if span:
            span.add_event(name, attributes=properties or {})
        
        logger.info("custom_event", event=name, properties=properties)
    
    def track_metric(self, name: str, value: float, properties: dict = None):
        """Track a custom metric."""
        span = trace.get_current_span()
        if span:
            span.set_attribute(f"metric.{name}", value)
            if properties:
                for k, v in properties.items():
                    span.set_attribute(f"metric.{name}.{k}", v)
        
        logger.info("custom_metric", metric=name, value=value, properties=properties)


# Import asyncio for the decorator
import asyncio
```

### Step 2: Update Catalog Service with Telemetry

Update `ecommerce-app/services/catalog-service/app/main.py`:

```python
"""Catalog Service with Application Insights telemetry."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from .config import get_settings
from .routes import router as products_router

# Import telemetry
import sys
sys.path.append('../..')
from shared.telemetry import (
    configure_telemetry, 
    instrument_fastapi, 
    TelemetryMiddleware,
    MetricsTracker
)

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()
settings = get_settings()

# Initialize metrics tracker
metrics = MetricsTracker("catalog-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    
    # Configure Application Insights
    configure_telemetry(
        service_name=settings.service_name,
        connection_string=settings.applicationinsights_connection_string
    )
    
    logger.info("catalog_service_starting", 
               service=settings.service_name,
               version=settings.service_version)
    
    # Track startup event
    metrics.track_event("service_started", {
        "service": settings.service_name,
        "version": settings.service_version
    })
    
    yield
    
    # Track shutdown event
    metrics.track_event("service_stopped", {
        "service": settings.service_name
    })
    
    logger.info("catalog_service_stopping")


app = FastAPI(
    title="Catalog Service",
    description="Product catalog management for Perfume & Dessert e-commerce",
    version=settings.service_version,
    lifespan=lifespan
)

# Add telemetry middleware
app.middleware("http")(TelemetryMiddleware(settings.service_name))

# Instrument FastAPI
instrument_fastapi(app)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(products_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.service_version
    }


@app.get("/ready")
async def readiness_check():
    """Readiness check - verifies database connectivity."""
    from .database import get_database
    try:
        db = get_database()
        await db.list_products(limit=1)
        
        # Track successful readiness check
        metrics.track_metric("readiness_check", 1.0, {"status": "success"})
        
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        logger.error("readiness_check_failed", error=str(e))
        
        # Track failed readiness check
        metrics.track_metric("readiness_check", 0.0, {"status": "failure", "error": str(e)})
        
        return {"status": "not_ready", "database": "disconnected", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
```

### Step 3: Add Custom Business Metrics

Update `ecommerce-app/services/catalog-service/app/routes.py` to track business metrics:

```python
"""Catalog Service API routes with telemetry."""

from datetime import datetime
from typing import Optional
from uuid import uuid4
import time

from fastapi import APIRouter, HTTPException, Query
import structlog

from .database import get_database

# Import telemetry
import sys
sys.path.append('../..')
from shared.telemetry import MetricsTracker, track_dependency

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/products", tags=["products"])
metrics = MetricsTracker("catalog-service")


@router.get("/")
async def list_products(
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """List all products with optional filtering."""
    start_time = time.time()
    
    logger.info("list_products", category=category, limit=limit, offset=offset)
    
    db = get_database()
    products = await db.list_products(category=category, limit=limit, offset=offset)
    
    # Track metrics
    duration_ms = (time.time() - start_time) * 1000
    metrics.track_metric("products_listed", len(products), {
        "category": category or "all",
        "duration_ms": duration_ms
    })
    
    # Track event for analytics
    metrics.track_event("products_viewed", {
        "category": category or "all",
        "count": len(products),
        "limit": limit,
        "offset": offset
    })
    
    return {
        "items": products,
        "count": len(products),
        "limit": limit,
        "offset": offset
    }


@router.get("/search")
async def search_products(
    q: str = Query(..., min_length=2, description="Search term"),
    limit: int = Query(20, ge=1, le=50)
):
    """Search products by name or description."""
    start_time = time.time()
    
    logger.info("search_products", query=q, limit=limit)
    
    db = get_database()
    products = await db.search_products(search_term=q, limit=limit)
    
    # Track search metrics
    duration_ms = (time.time() - start_time) * 1000
    metrics.track_metric("product_search", len(products), {
        "query": q,
        "duration_ms": duration_ms,
        "results_found": len(products) > 0
    })
    
    # Track search event
    metrics.track_event("product_searched", {
        "query": q,
        "results_count": len(products),
        "duration_ms": duration_ms
    })
    
    return {
        "items": products,
        "count": len(products),
        "query": q
    }


@router.post("/", status_code=201)
async def create_product(product: dict):
    """Create a new product."""
    start_time = time.time()
    
    logger.info("create_product", name=product.get("name"))
    
    # Add metadata
    product["id"] = str(uuid4())
    product["created_at"] = datetime.utcnow().isoformat()
    product["updated_at"] = datetime.utcnow().isoformat()
    product["is_active"] = True
    
    db = get_database()
    created = await db.create_product(product)
    
    # Track product creation
    duration_ms = (time.time() - start_time) * 1000
    metrics.track_event("product_created", {
        "product_id": created["id"],
        "category": created.get("category"),
        "price": created.get("price"),
        "duration_ms": duration_ms
    })
    
    metrics.track_metric("products_created_total", 1, {
        "category": created.get("category")
    })
    
    logger.info("product_created", product_id=created["id"])
    return created


# ... rest of routes with similar telemetry additions
```

### Step 4: Create Telemetry Dashboard Query Library

Create `ecommerce-app/monitoring/queries/app-insights-queries.kql`:

```kql
// ============================================================
// APPLICATION INSIGHTS KQL QUERY LIBRARY
// ============================================================

// 1. Request Performance Overview
requests
| where timestamp > ago(1h)
| summarize 
    RequestCount = count(),
    AvgDuration = avg(duration),
    P50 = percentile(duration, 50),
    P95 = percentile(duration, 95),
    P99 = percentile(duration, 99),
    FailureRate = 100.0 * countif(success == false) / count()
| project RequestCount, AvgDuration, P50, P95, P99, FailureRate

// 2. Requests by Service
requests
| where timestamp > ago(1h)
| extend Service = tostring(customDimensions["service.name"])
| summarize 
    Count = count(),
    AvgDuration = avg(duration),
    Failures = countif(success == false)
    by Service
| order by Count desc

// 3. Slowest Endpoints
requests
| where timestamp > ago(1h)
| summarize 
    AvgDuration = avg(duration),
    P95 = percentile(duration, 95),
    Count = count()
    by name
| where Count > 10
| order by P95 desc
| take 10

// 4. Error Rate Trend
requests
| where timestamp > ago(24h)
| summarize 
    Total = count(),
    Failed = countif(success == false)
    by bin(timestamp, 15m)
| extend ErrorRate = 100.0 * Failed / Total
| project timestamp, ErrorRate

// 5. Dependency Performance (Cosmos DB, Redis, etc.)
dependencies
| where timestamp > ago(1h)
| summarize 
    Calls = count(),
    AvgDuration = avg(duration),
    FailureRate = 100.0 * countif(success == false) / count()
    by type, target
| order by AvgDuration desc

// 6. Exception Summary
exceptions
| where timestamp > ago(1h)
| summarize Count = count() by type, outerMessage
| order by Count desc
| take 20

// 7. Custom Events (Business Metrics)
customEvents
| where timestamp > ago(1h)
| where name in ("product_searched", "product_created", "order_created")
| summarize Count = count() by name
| render piechart

// 8. End-to-End Transaction Trace
union requests, dependencies, traces, exceptions
| where operation_Id == "YOUR_OPERATION_ID"
| order by timestamp asc
| project timestamp, itemType, name, duration, success, message

// 9. Service Health Dashboard
let timeRange = ago(1h);
let requests_summary = requests
| where timestamp > timeRange
| summarize 
    RequestCount = count(),
    FailureCount = countif(success == false),
    AvgDuration = avg(duration)
    by cloud_RoleName;
let dependency_summary = dependencies
| where timestamp > timeRange
| summarize 
    DepCalls = count(),
    DepFailures = countif(success == false)
    by cloud_RoleName;
requests_summary
| join kind=leftouter dependency_summary on cloud_RoleName
| project 
    Service = cloud_RoleName,
    Requests = RequestCount,
    RequestFailures = FailureCount,
    AvgLatency = AvgDuration,
    DependencyCalls = DepCalls,
    DependencyFailures = DepFailures

// 10. Real-time Performance Monitoring
requests
| where timestamp > ago(5m)
| summarize 
    Count = count(),
    AvgDuration = avg(duration),
    MaxDuration = max(duration)
    by bin(timestamp, 30s), name
| render timechart
```

---

## 🧪 Verification Checklist

Before moving to the next session, ensure you have:

- [ ] Telemetry module created in shared package
- [ ] All services instrumented with Application Insights
- [ ] Custom metrics tracking business events
- [ ] Dependency tracking for Cosmos DB, Redis
- [ ] KQL query library created
- [ ] Telemetry visible in Azure Portal

---

## 💡 Viewing Telemetry in Azure Portal

1. Navigate to your Application Insights resource
2. **Application Map**: Visual service dependency graph
3. **Performance**: Request latency and throughput
4. **Failures**: Exception tracking and analysis
5. **Logs**: Run KQL queries in Log Analytics
6. **Metrics**: Custom metric dashboards

---

## 📖 Key Takeaways

1. **OpenTelemetry** provides vendor-agnostic instrumentation
2. **Correlation IDs** link requests across services
3. **Custom events/metrics** track business KPIs
4. **Dependency tracking** shows external service health

---

## 🔜 Next Session Preview

**Session 8: Log Analytics & KQL Mastery**
- Advanced KQL query techniques
- Creating saved queries
- Building dashboards from queries

---

## 📚 Additional Resources

- [Application Insights Overview](https://docs.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview)
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- [KQL Quick Reference](https://docs.microsoft.com/en-us/azure/data-explorer/kql-quick-reference)
