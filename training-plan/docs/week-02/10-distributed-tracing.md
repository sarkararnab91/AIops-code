# Session 10: Distributed Tracing

## 📋 Session Details
- **Duration**: 1 hour
- **Week**: 2, Day 5 (Friday)
- **Prerequisites**: Sessions 1-9 completed
- **Deliverable**: End-to-end request tracing working

---

## 🎯 Learning Objectives

By the end of this session, you will:
1. Understand W3C Trace Context standard
2. Implement correlation ID propagation
3. Trace requests across all services
4. Debug performance issues using traces

---

## 📚 Concepts

### Distributed Tracing Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       DISTRIBUTED TRACING FLOW                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Frontend                trace_id: abc123, span_id: 001                    │
│      │                                                                       │
│      │ POST /api/v1/orders                                                   │
│      │ traceparent: 00-abc123-001-01                                        │
│      ▼                                                                       │
│   ┌─────────────┐                                                           │
│   │   Ingress   │        trace_id: abc123, span_id: 002, parent: 001       │
│   └──────┬──────┘                                                           │
│          │                                                                   │
│          ▼                                                                   │
│   ┌─────────────┐                                                           │
│   │   Order     │        trace_id: abc123, span_id: 003, parent: 002       │
│   │   Service   │                                                           │
│   └──────┬──────┘                                                           │
│          │                                                                   │
│    ┌─────┼──────────────────────┐                                           │
│    │     │                      │                                           │
│    ▼     ▼                      ▼                                           │
│ ┌─────┐ ┌─────────┐      ┌──────────┐                                      │
│ │Cart │ │Inventory│      │ Payment  │                                      │
│ │Svc  │ │ Service │      │ Service  │                                      │
│ │004  │ │  005    │      │   006    │                                      │
│ └─────┘ └─────────┘      └──────────┘                                      │
│                                │                                            │
│                                ▼                                            │
│                          ┌──────────┐                                       │
│                          │ Cosmos DB│  span_id: 007                        │
│                          └──────────┘                                       │
│                                                                              │
│   All spans share trace_id: abc123                                          │
│   Each span has unique span_id                                              │
│   Parent-child relationships form trace tree                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### W3C Trace Context Headers

```
traceparent: 00-{trace-id}-{span-id}-{flags}
            │   │          │         │
            │   │          │         └── Sampling flags
            │   │          └──────────── Current span ID (16 hex chars)
            │   └─────────────────────── Trace ID (32 hex chars)
            └─────────────────────────── Version

Example:
traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01
```

---

## 🛠️ Hands-On Exercise

### Step 1: Create Tracing Middleware

Update `ecommerce-app/shared/telemetry.py` to add tracing utilities:

```python
"""Enhanced telemetry with distributed tracing."""

import os
import time
from typing import Optional, Dict, Any
from functools import wraps
from contextvars import ContextVar
import uuid

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode, SpanKind
from opentelemetry.propagate import extract, inject
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
import structlog

logger = structlog.get_logger()

# Context variable for correlation ID
correlation_id_var: ContextVar[str] = ContextVar('correlation_id', default='')

# Propagator for W3C Trace Context
propagator = TraceContextTextMapPropagator()


def get_correlation_id() -> str:
    """Get current correlation ID from context."""
    return correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID in context."""
    correlation_id_var.set(correlation_id)


class TracingMiddleware:
    """Middleware for distributed tracing in FastAPI."""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.tracer = trace.get_tracer(service_name)
    
    async def __call__(self, request, call_next):
        # Extract trace context from incoming headers
        carrier = {}
        for key, value in request.headers.items():
            carrier[key.lower()] = value
        
        context = extract(carrier)
        
        # Get or generate correlation ID
        correlation_id = request.headers.get(
            "x-correlation-id", 
            str(uuid.uuid4())
        )
        set_correlation_id(correlation_id)
        
        # Start span with extracted context
        with self.tracer.start_as_current_span(
            f"{request.method} {request.url.path}",
            context=context,
            kind=SpanKind.SERVER,
            attributes={
                "http.method": request.method,
                "http.url": str(request.url),
                "http.route": request.url.path,
                "http.host": request.headers.get("host", ""),
                "service.name": self.service_name,
                "correlation_id": correlation_id,
            }
        ) as span:
            start_time = time.time()
            
            try:
                response = await call_next(request)
                
                # Add response info to span
                span.set_attribute("http.status_code", response.status_code)
                
                if response.status_code >= 500:
                    span.set_status(Status(StatusCode.ERROR))
                elif response.status_code >= 400:
                    span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
                else:
                    span.set_status(Status(StatusCode.OK))
                
                # Add trace headers to response
                response.headers["x-correlation-id"] = correlation_id
                response.headers["x-trace-id"] = format(span.get_span_context().trace_id, '032x')
                
                return response
                
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            
            finally:
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("http.duration_ms", duration_ms)
                
                logger.info(
                    "request_completed",
                    method=request.method,
                    path=request.url.path,
                    status=response.status_code if 'response' in dir() else 500,
                    duration_ms=round(duration_ms, 2),
                    correlation_id=correlation_id,
                    trace_id=format(span.get_span_context().trace_id, '032x')
                )


class TracingHTTPClient:
    """HTTP client wrapper that propagates trace context."""
    
    def __init__(self, base_url: str, service_name: str):
        self.base_url = base_url.rstrip('/')
        self.service_name = service_name
        self.tracer = trace.get_tracer(service_name)
    
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
                async with httpx.AsyncClient() as client:
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
    
    def _extract_service_name(self, path: str) -> str:
        """Extract target service name from path."""
        parts = path.split('/')
        for part in parts:
            if part in ['products', 'catalog']:
                return 'catalog-service'
            elif part in ['cart']:
                return 'cart-service'
            elif part in ['orders']:
                return 'order-service'
            elif part in ['payments']:
                return 'payment-service'
            elif part in ['users']:
                return 'user-service'
            elif part in ['inventory']:
                return 'inventory-service'
        return 'unknown-service'


def trace_operation(name: str, kind: SpanKind = SpanKind.INTERNAL):
    """Decorator to create a traced operation."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = trace.get_tracer(__name__)
            
            with tracer.start_as_current_span(
                name,
                kind=kind,
                attributes={
                    "correlation_id": get_correlation_id()
                }
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
            tracer = trace.get_tracer(__name__)
            
            with tracer.start_as_current_span(
                name,
                kind=kind,
                attributes={
                    "correlation_id": get_correlation_id()
                }
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
    """Add attribute to current span."""
    span = trace.get_current_span()
    if span:
        span.set_attribute(key, value)


def add_span_event(name: str, attributes: Dict[str, Any] = None) -> None:
    """Add event to current span."""
    span = trace.get_current_span()
    if span:
        span.add_event(name, attributes=attributes or {})
```

### Step 2: Update Order Service with Tracing

Show how Order Service calls other services with trace propagation:

```python
"""Order Service with full distributed tracing."""

from shared.telemetry import (
    TracingMiddleware,
    TracingHTTPClient,
    trace_operation,
    add_span_attribute,
    add_span_event,
    get_correlation_id
)

# ... existing imports ...

# HTTP clients for other services
inventory_client = TracingHTTPClient(
    base_url="http://inventory-service:8002",
    service_name="order-service"
)

cart_client = TracingHTTPClient(
    base_url="http://cart-service:8004", 
    service_name="order-service"
)

payment_client = TracingHTTPClient(
    base_url="http://payment-service:8005",
    service_name="order-service"
)


@trace_operation("create_order_flow")
async def create_order_with_tracing(
    user_id: str,
    items: list,
    shipping_address: dict
) -> dict:
    """Create order with full tracing across services."""
    
    add_span_attribute("user_id", user_id)
    add_span_attribute("item_count", len(items))
    
    # Step 1: Reserve inventory
    add_span_event("reserving_inventory")
    for item in items:
        response = await inventory_client.request(
            "POST",
            "/api/v1/inventory/reserve",
            json={
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "order_id": "pending"
            }
        )
        if response["status_code"] != 200:
            add_span_event("inventory_reservation_failed", {
                "product_id": item["product_id"]
            })
            raise Exception(f"Failed to reserve inventory: {item['product_id']}")
    
    add_span_event("inventory_reserved")
    
    # Step 2: Create payment
    add_span_event("creating_payment")
    total = sum(item["price"] * item["quantity"] for item in items)
    payment_response = await payment_client.request(
        "POST",
        "/api/v1/payments",
        json={
            "order_id": "pending",
            "user_id": user_id,
            "amount": total,
            "method": "credit_card"
        }
    )
    
    if payment_response["status_code"] != 201:
        add_span_event("payment_creation_failed")
        raise Exception("Failed to create payment")
    
    payment_id = payment_response["data"]["id"]
    add_span_attribute("payment_id", payment_id)
    add_span_event("payment_created")
    
    # Step 3: Process payment
    add_span_event("processing_payment")
    process_response = await payment_client.request(
        "POST",
        f"/api/v1/payments/{payment_id}/process",
        params={"order_id": "pending"}
    )
    
    if process_response["data"]["status"] != "authorized":
        add_span_event("payment_failed", {
            "reason": process_response["data"].get("failure_reason")
        })
        raise Exception("Payment failed")
    
    add_span_event("payment_authorized")
    
    # Step 4: Clear cart
    add_span_event("clearing_cart")
    await cart_client.request("DELETE", "/api/v1/cart")
    
    add_span_event("order_completed")
    
    return {
        "order_id": str(uuid.uuid4()),
        "payment_id": payment_id,
        "total": total,
        "status": "confirmed"
    }
```

### Step 3: KQL Queries for Trace Analysis

```kql
// Query 1: Full transaction trace
let target_operation = "YOUR_OPERATION_ID";
union 
    (requests | where operation_Id == target_operation),
    (dependencies | where operation_Id == target_operation),
    (traces | where operation_Id == target_operation),
    (exceptions | where operation_Id == target_operation)
| project 
    timestamp,
    Type = itemType,
    Service = cloud_RoleName,
    Name = coalesce(name, message),
    Duration = duration,
    Success = success
| order by timestamp asc

// Query 2: Trace waterfall view
requests
| where operation_Id == "YOUR_OPERATION_ID"
| project 
    StartTime = timestamp,
    EndTime = timestamp + duration * 1ms,
    Service = cloud_RoleName,
    Name = name,
    Duration = duration
| union (
    dependencies
    | where operation_Id == "YOUR_OPERATION_ID"
    | project
        StartTime = timestamp,
        EndTime = timestamp + duration * 1ms,
        Service = cloud_RoleName,
        Name = strcat(type, " → ", target),
        Duration = duration
)
| order by StartTime asc

// Query 3: Slow traces analysis
requests
| where timestamp > ago(1h)
| where duration > 2000  // > 2 seconds
| project 
    operation_Id,
    timestamp,
    name,
    duration,
    cloud_RoleName
| join kind=inner (
    dependencies
    | where timestamp > ago(1h)
    | summarize 
        DependencyCount = count(),
        TotalDependencyTime = sum(duration),
        SlowDependencies = countif(duration > 500)
    by operation_Id
) on operation_Id
| project 
    timestamp,
    RequestName = name,
    RequestDuration = duration,
    DependencyCount,
    TotalDependencyTime,
    SlowDependencies,
    operation_Id
| order by RequestDuration desc
| take 20

// Query 4: Service-to-service call map
dependencies
| where timestamp > ago(1h)
| extend 
    SourceService = cloud_RoleName,
    TargetService = target
| summarize 
    Calls = count(),
    AvgDuration = avg(duration),
    Failures = countif(success == false)
by SourceService, TargetService
| order by Calls desc

// Query 5: Cross-service error correlation
let error_operations = requests
| where timestamp > ago(1h)
| where success == false
| distinct operation_Id;
dependencies
| where timestamp > ago(1h)
| where operation_Id in (error_operations)
| summarize 
    ErrorOperations = dcount(operation_Id),
    TotalCalls = count()
by type, target, name
| order by ErrorOperations desc
```

### Step 4: Create Trace Visualization in Workbook

Add to your workbook:

```json
{
  "type": 3,
  "content": {
    "version": "KqlItem/1.0",
    "query": "// Service Dependency Map\ndependencies\n| where timestamp > ago(1h)\n| summarize Calls = count() by Source = cloud_RoleName, Target = target\n| render table",
    "size": 0,
    "title": "Service Dependency Map",
    "queryType": 0,
    "visualization": "table"
  },
  "name": "dependency-map"
}
```

---

## 🧪 Verification Checklist

Before completing Week 2, ensure you have:

- [ ] Trace context propagation working across services
- [ ] Correlation ID passed in all requests
- [ ] Can view full request trace in Application Insights
- [ ] Service dependency map visible
- [ ] Slow trace analysis queries working
- [ ] Workbook showing trace data

---

## 📊 Week 1-2 Summary

You have now completed the **Traditional Monitoring** phase:

| Component | Status |
|-----------|--------|
| Azure Infrastructure | ✅ AKS, Cosmos DB, Redis, Service Bus |
| Microservices | ✅ 7 FastAPI services |
| Frontend | ✅ Vue.js application |
| Application Insights | ✅ Full instrumentation |
| Log Analytics | ✅ KQL query library |
| Alerts | ✅ Metric and log alerts |
| Dashboards | ✅ Azure Workbooks |
| Distributed Tracing | ✅ End-to-end correlation |

---

## 🔜 Week 3-4 Preview

**ML-Based AIOps**
- Failure simulation and chaos engineering
- Anomaly detection with Isolation Forest
- Capacity forecasting with Prophet
- ML-based correlation and root cause analysis

---

## 📚 Additional Resources

- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- [Application Map](https://docs.microsoft.com/en-us/azure/azure-monitor/app/app-map)
- [Transaction Diagnostics](https://docs.microsoft.com/en-us/azure/azure-monitor/app/transaction-diagnostics)
