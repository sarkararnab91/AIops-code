"""
Catalog Service - Product Management for E-Commerce
Handles product catalog for Perfume & Dessert categories.
"""

import os
import uuid
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import (
    configure_telemetry,
    instrument_fastapi,
    TracingMiddleware,
    trace_operation,
    add_span_attribute,
    track_custom_event,
    get_cosmos_client,
    get_redis_client,
    TelemetryLogger,
)


# Configuration
SERVICE_NAME = "catalog-service"
CONTAINER_NAME = "products"
CACHE_TTL = 300  # 5 minutes

# Initialize telemetry
configure_telemetry(SERVICE_NAME)
logger = TelemetryLogger(SERVICE_NAME)


# =============================================================================
# MODELS
# =============================================================================

class ProductCreate(BaseModel):
    """Request model for creating a product."""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., max_length=2000)
    category: str = Field(..., pattern="^(perfume|dessert)$")
    subcategory: str = Field(..., min_length=1)
    price: float = Field(..., gt=0)
    currency: str = Field(default="USD")
    image_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    attributes: dict = Field(default_factory=dict)


class ProductUpdate(BaseModel):
    """Request model for updating a product."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    price: Optional[float] = Field(None, gt=0)
    image_url: Optional[str] = None
    tags: Optional[List[str]] = None
    attributes: Optional[dict] = None
    is_active: Optional[bool] = None


class Product(BaseModel):
    """Product model."""
    id: str
    name: str
    description: str
    category: str
    subcategory: str
    price: float
    currency: str
    image_url: Optional[str] = None
    tags: List[str] = []
    attributes: dict = {}
    is_active: bool = True
    created_at: str
    updated_at: str


class ProductList(BaseModel):
    """Response model for product list."""
    items: List[Product]
    total: int
    page: int
    page_size: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    timestamp: str


# =============================================================================
# LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan for managing connections."""
    logger.info("Starting Catalog Service")
    
    # Initialize database connections
    cosmos = await get_cosmos_client()
    redis = await get_redis_client()
    
    # Store in app state
    app.state.cosmos = cosmos
    app.state.redis = redis
    
    logger.info("Catalog Service started successfully")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Catalog Service")
    await cosmos.close()
    await redis.close()


# =============================================================================
# APP INITIALIZATION
# =============================================================================

app = FastAPI(
    title="Catalog Service",
    description="Product catalog management for Perfume & Dessert e-commerce",
    version="1.0.0",
    lifespan=lifespan
)

# Add middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TracingMiddleware, service_name=SERVICE_NAME)

# Instrument with OpenTelemetry
instrument_fastapi(app)


# =============================================================================
# HELPERS
# =============================================================================

def get_cache_key(product_id: str) -> str:
    """Generate cache key for a product."""
    return f"product:{product_id}"


def get_category_cache_key(category: str, page: int, page_size: int) -> str:
    """Generate cache key for category listing."""
    return f"products:{category}:{page}:{page_size}"


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        service=SERVICE_NAME,
        timestamp=datetime.utcnow().isoformat()
    )


@app.get("/ready")
async def readiness_check():
    """Readiness check - verifies database connections."""
    try:
        # Check Cosmos DB
        await app.state.cosmos.client.read_database(app.state.cosmos.database_name)
        
        # Check Redis
        await app.state.redis.client.ping()
        
        return {"status": "ready"}
    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service not ready")


@app.post("/api/v1/products", response_model=Product, status_code=201)
@trace_operation("create_product")
async def create_product(product: ProductCreate):
    """Create a new product."""
    product_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    product_data = {
        "id": product_id,
        **product.model_dump(),
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    
    add_span_attribute("product.id", product_id)
    add_span_attribute("product.category", product.category)
    add_span_attribute("product.price", product.price)
    
    # Save to Cosmos DB
    await app.state.cosmos.create_item(CONTAINER_NAME, product_data)
    
    # Track event
    track_custom_event(
        "product_created",
        properties={
            "product_id": product_id,
            "category": product.category,
            "subcategory": product.subcategory
        },
        measurements={"price": product.price}
    )
    
    logger.info(
        "Product created",
        product_id=product_id,
        category=product.category
    )
    
    return Product(**product_data)


@app.get("/api/v1/products/{product_id}", response_model=Product)
@trace_operation("get_product")
async def get_product(product_id: str):
    """Get a product by ID."""
    add_span_attribute("product.id", product_id)
    
    # Try cache first
    cache_key = get_cache_key(product_id)
    cached = await app.state.redis.get(cache_key)
    
    if cached:
        import json
        add_span_attribute("cache.hit", True)
        return Product(**json.loads(cached))
    
    add_span_attribute("cache.hit", False)
    
    # Query Cosmos DB
    query = "SELECT * FROM c WHERE c.id = @id AND c.is_active = true"
    parameters = [{"name": "@id", "value": product_id}]
    
    items = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        query,
        parameters
    )
    
    if not items:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product = items[0]
    
    # Cache the result
    import json
    await app.state.redis.set(
        cache_key,
        json.dumps(product),
        ttl_seconds=CACHE_TTL
    )
    
    return Product(**product)


@app.get("/api/v1/products", response_model=ProductList)
@trace_operation("list_products")
async def list_products(
    category: Optional[str] = Query(None, pattern="^(perfume|dessert)$"),
    subcategory: Optional[str] = None,
    search: Optional[str] = None,
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """List products with filters and pagination."""
    add_span_attribute("filter.category", category or "all")
    add_span_attribute("pagination.page", page)
    add_span_attribute("pagination.page_size", page_size)
    
    # Build query
    conditions = ["c.is_active = true"]
    parameters = []
    
    if category:
        conditions.append("c.category = @category")
        parameters.append({"name": "@category", "value": category})
    
    if subcategory:
        conditions.append("c.subcategory = @subcategory")
        parameters.append({"name": "@subcategory", "value": subcategory})
    
    if search:
        conditions.append("CONTAINS(LOWER(c.name), LOWER(@search))")
        parameters.append({"name": "@search", "value": search})
    
    if min_price is not None:
        conditions.append("c.price >= @min_price")
        parameters.append({"name": "@min_price", "value": min_price})
    
    if max_price is not None:
        conditions.append("c.price <= @max_price")
        parameters.append({"name": "@max_price", "value": max_price})
    
    where_clause = " AND ".join(conditions)
    offset = (page - 1) * page_size
    
    # Count query
    count_query = f"SELECT VALUE COUNT(1) FROM c WHERE {where_clause}"
    count_result = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        count_query,
        parameters
    )
    total = count_result[0] if count_result else 0
    
    # Data query with pagination
    data_query = f"""
        SELECT * FROM c 
        WHERE {where_clause}
        ORDER BY c.created_at DESC
        OFFSET @offset LIMIT @limit
    """
    parameters.extend([
        {"name": "@offset", "value": offset},
        {"name": "@limit", "value": page_size}
    ])
    
    items = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        data_query,
        parameters
    )
    
    add_span_attribute("result.count", len(items))
    add_span_attribute("result.total", total)
    
    # Track search event
    if search:
        track_custom_event(
            "product_searched",
            properties={"query": search, "category": category or "all"},
            measurements={"results_count": len(items)}
        )
    
    return ProductList(
        items=[Product(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size
    )


@app.put("/api/v1/products/{product_id}", response_model=Product)
@trace_operation("update_product")
async def update_product(product_id: str, updates: ProductUpdate):
    """Update a product."""
    add_span_attribute("product.id", product_id)
    
    # Get current product to find partition key
    current = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT * FROM c WHERE c.id = @id",
        [{"name": "@id", "value": product_id}]
    )
    
    if not current:
        raise HTTPException(status_code=404, detail="Product not found")
    
    current_product = current[0]
    
    # Build updates
    update_data = {
        k: v for k, v in updates.model_dump().items() 
        if v is not None
    }
    update_data["updated_at"] = datetime.utcnow().isoformat()
    
    # Update in Cosmos DB
    result = await app.state.cosmos.update_item(
        CONTAINER_NAME,
        product_id,
        current_product["category"],  # Partition key
        update_data
    )
    
    # Invalidate cache
    await app.state.redis.delete(get_cache_key(product_id))
    
    logger.info("Product updated", product_id=product_id)
    
    return Product(**result)


@app.delete("/api/v1/products/{product_id}", status_code=204)
@trace_operation("delete_product")
async def delete_product(product_id: str):
    """Soft delete a product."""
    add_span_attribute("product.id", product_id)
    
    # Get current product
    current = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT * FROM c WHERE c.id = @id",
        [{"name": "@id", "value": product_id}]
    )
    
    if not current:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Soft delete
    await app.state.cosmos.update_item(
        CONTAINER_NAME,
        product_id,
        current[0]["category"],
        {
            "is_active": False,
            "updated_at": datetime.utcnow().isoformat()
        }
    )
    
    # Invalidate cache
    await app.state.redis.delete(get_cache_key(product_id))
    
    logger.info("Product deleted", product_id=product_id)


@app.get("/api/v1/products/categories/{category}", response_model=ProductList)
@trace_operation("list_by_category")
async def list_by_category(
    category: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """List products by category."""
    if category not in ["perfume", "dessert"]:
        raise HTTPException(status_code=400, detail="Invalid category")
    
    # Track category view
    track_custom_event(
        "category_viewed",
        properties={"category": category},
        measurements={"page": page}
    )
    
    return await list_products(
        category=category,
        page=page,
        page_size=page_size
    )


@app.get("/api/v1/products/featured", response_model=List[Product])
@trace_operation("get_featured_products")
async def get_featured_products(limit: int = Query(10, ge=1, le=50)):
    """Get featured products (random selection from each category)."""
    
    # Get featured perfumes
    perfumes = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        """
            SELECT TOP @limit * FROM c 
            WHERE c.category = 'perfume' AND c.is_active = true
            ORDER BY c.created_at DESC
        """,
        [{"name": "@limit", "value": limit // 2}]
    )
    
    # Get featured desserts
    desserts = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        """
            SELECT TOP @limit * FROM c 
            WHERE c.category = 'dessert' AND c.is_active = true
            ORDER BY c.created_at DESC
        """,
        [{"name": "@limit", "value": limit // 2}]
    )
    
    featured = perfumes + desserts
    
    track_custom_event(
        "featured_products_viewed",
        measurements={"count": len(featured)}
    )
    
    return [Product(**p) for p in featured]


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8001")),
        reload=os.getenv("ENV", "development") == "development"
    )
