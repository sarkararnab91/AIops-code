"""Catalog Service with Application Insights telemetry."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
import os
import sys

from .config import get_settings
from .routes import router as products_router

# Import telemetry
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

try:
    from shared.telemetry import (
        configure_telemetry, 
        instrument_fastapi, 
        TelemetryMiddleware,
        MetricsTracker
    )
except ImportError:
    # Fallback to prevent crash if shared not found
    print("WARNING: Telemetry module not found. Telemetry disabled.")
    def configure_telemetry(*args, **kwargs): pass
    def instrument_fastapi(*args, **kwargs): pass
    class TelemetryMiddleware:
        def __init__(self, *args, **kwargs): pass
        async def __call__(self, request, call_next): return await call_next(request)
    class MetricsTracker:
        def __init__(self, *args, **kwargs): pass
        def track_event(self, *args, **kwargs): pass
        def track_metric(self, *args, **kwargs): pass

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
    conn_str = getattr(settings, 'applicationinsights_connection_string', os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"))
    configure_telemetry(
        service_name=settings.service_name,
        connection_string=conn_str
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
