"""Catalog Service API routes with telemetry."""

from datetime import datetime
from typing import Optional
from uuid import uuid4
import time
import sys
import os

from fastapi import APIRouter, HTTPException, Query
import structlog

from .database import get_database

# Import telemetry
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
try:
    from shared.telemetry import MetricsTracker, track_dependency
except ImportError:
    class MetricsTracker:
        def __init__(self, *args): pass
        def track_metric(self, *args, **kwargs): pass
        def track_event(self, *args, **kwargs): pass
    def track_dependency(*args, **kwargs):
        def decorator(f): return f
        return decorator

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


@router.get("/{product_id}")
async def get_product(product_id: str, category: str = Query(...)):
    """Get a product by ID."""
    logger.info("get_product", product_id=product_id, category=category)
    
    db = get_database()
    product = await db.get_product(product_id, category)
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return product


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


@router.put("/{product_id}")
async def update_product(product_id: str, category: str, updates: dict):
    """Update a product."""
    logger.info("update_product", product_id=product_id)
    
    db = get_database()
    existing = await db.get_product(product_id, category)
    
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Merge updates
    existing.update(updates)
    existing["updated_at"] = datetime.utcnow().isoformat()
    
    updated = await db.update_product(existing)
    return updated


@router.delete("/{product_id}")
async def delete_product(product_id: str, category: str):
    """Delete a product (soft delete)."""
    logger.info("delete_product", product_id=product_id)
    
    db = get_database()
    success = await db.delete_product(product_id, category)
    
    if not success:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return {"message": "Product deleted", "product_id": product_id}


@router.get("/categories/list")
async def list_categories():
    """List available product categories."""
    return {
        "categories": [
            {"id": "perfumes", "name": "Perfumes", "description": "Luxury fragrances and colognes"},
            {"id": "desserts", "name": "Desserts", "description": "Gourmet cakes, pastries, and confections"}
        ]
    }
