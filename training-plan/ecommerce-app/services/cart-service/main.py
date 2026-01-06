"""
Cart Service - Shopping Cart Management
Handles cart operations with Redis for fast access.
"""

import os
import json
import uuid
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import (
    configure_telemetry,
    instrument_fastapi,
    TracingMiddleware,
    TracingHTTPClient,
    trace_operation,
    add_span_attribute,
    track_custom_event,
    get_redis_client,
    TelemetryLogger,
)


# Configuration
SERVICE_NAME = "cart-service"
CART_TTL = 604800  # 7 days in seconds
CATALOG_SERVICE_URL = os.getenv("CATALOG_SERVICE_URL", "http://catalog-service:8001")

# Initialize telemetry
configure_telemetry(SERVICE_NAME)
logger = TelemetryLogger(SERVICE_NAME)


# =============================================================================
# MODELS
# =============================================================================

class CartItem(BaseModel):
    """Cart item model."""
    product_id: str
    product_name: str
    quantity: int = Field(..., ge=1)
    unit_price: float = Field(..., gt=0)
    image_url: Optional[str] = None


class CartItemAdd(BaseModel):
    """Request model for adding item to cart."""
    product_id: str
    quantity: int = Field(default=1, ge=1)


class CartItemUpdate(BaseModel):
    """Request model for updating cart item quantity."""
    quantity: int = Field(..., ge=0)  # 0 means remove


class Cart(BaseModel):
    """Shopping cart model."""
    user_id: str
    items: List[CartItem]
    item_count: int
    subtotal: float
    updated_at: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    timestamp: str


# =============================================================================
# LIFESPAN & APP
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan."""
    logger.info("Starting Cart Service")
    
    redis = await get_redis_client()
    app.state.redis = redis
    app.state.catalog_client = TracingHTTPClient(CATALOG_SERVICE_URL, SERVICE_NAME)
    
    logger.info("Cart Service started successfully")
    yield
    
    await redis.close()


app = FastAPI(
    title="Cart Service",
    description="Shopping cart management with Redis caching",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TracingMiddleware, service_name=SERVICE_NAME)
instrument_fastapi(app)


# =============================================================================
# HELPERS
# =============================================================================

def get_cart_key(user_id: str) -> str:
    """Generate Redis key for user's cart."""
    return f"cart:{user_id}"


async def get_cart_data(user_id: str) -> dict:
    """Get cart data from Redis."""
    redis = app.state.redis
    cart_key = get_cart_key(user_id)
    
    data = await redis.hgetall(cart_key)
    
    if not data:
        return {"items": {}, "updated_at": datetime.utcnow().isoformat()}
    
    items = {}
    for product_id, item_json in data.items():
        if product_id != "_meta":
            items[product_id] = json.loads(item_json)
    
    meta = json.loads(data.get("_meta", "{}"))
    
    return {
        "items": items,
        "updated_at": meta.get("updated_at", datetime.utcnow().isoformat())
    }


async def save_cart_data(user_id: str, items: dict) -> None:
    """Save cart data to Redis."""
    redis = app.state.redis
    cart_key = get_cart_key(user_id)
    
    # Build mapping
    mapping = {}
    for product_id, item in items.items():
        mapping[product_id] = json.dumps(item)
    
    # Add metadata
    mapping["_meta"] = json.dumps({
        "updated_at": datetime.utcnow().isoformat()
    })
    
    if mapping:
        await redis.hset(cart_key, mapping)
        # Set TTL
        await redis.client.expire(cart_key, CART_TTL)
    else:
        await redis.delete(cart_key)


def build_cart_response(user_id: str, cart_data: dict) -> Cart:
    """Build Cart response from data."""
    items = list(cart_data["items"].values())
    item_count = sum(item["quantity"] for item in items)
    subtotal = sum(item["unit_price"] * item["quantity"] for item in items)
    
    return Cart(
        user_id=user_id,
        items=[CartItem(**item) for item in items],
        item_count=item_count,
        subtotal=round(subtotal, 2),
        updated_at=cart_data["updated_at"]
    )


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


@app.get("/api/v1/cart/{user_id}", response_model=Cart)
@trace_operation("get_cart")
async def get_cart(user_id: str):
    """Get user's shopping cart."""
    add_span_attribute("user_id", user_id)
    
    cart_data = await get_cart_data(user_id)
    
    add_span_attribute("cart.item_count", len(cart_data["items"]))
    
    return build_cart_response(user_id, cart_data)


@app.post("/api/v1/cart/{user_id}/items", response_model=Cart)
@trace_operation("add_to_cart")
async def add_to_cart(user_id: str, item: CartItemAdd):
    """Add item to cart."""
    add_span_attribute("user_id", user_id)
    add_span_attribute("product_id", item.product_id)
    add_span_attribute("quantity", item.quantity)
    
    # Get product details from catalog
    try:
        response = await app.state.catalog_client.get(
            f"/api/v1/products/{item.product_id}"
        )
        
        if response["status_code"] != 200:
            raise HTTPException(status_code=404, detail="Product not found")
        
        product = response["data"]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch product", product_id=item.product_id, error=str(e))
        raise HTTPException(status_code=503, detail="Catalog service unavailable")
    
    # Get current cart
    cart_data = await get_cart_data(user_id)
    items = cart_data["items"]
    
    # Add or update item
    if item.product_id in items:
        items[item.product_id]["quantity"] += item.quantity
    else:
        items[item.product_id] = {
            "product_id": item.product_id,
            "product_name": product["name"],
            "quantity": item.quantity,
            "unit_price": product["price"],
            "image_url": product.get("image_url")
        }
    
    # Save cart
    await save_cart_data(user_id, items)
    
    # Track event
    track_custom_event(
        "cart_item_added",
        properties={
            "user_id": user_id,
            "product_id": item.product_id,
            "product_name": product["name"]
        },
        measurements={
            "quantity": item.quantity,
            "unit_price": product["price"]
        }
    )
    
    logger.info(
        "Item added to cart",
        user_id=user_id,
        product_id=item.product_id,
        quantity=item.quantity
    )
    
    cart_data["items"] = items
    cart_data["updated_at"] = datetime.utcnow().isoformat()
    
    return build_cart_response(user_id, cart_data)


@app.put("/api/v1/cart/{user_id}/items/{product_id}", response_model=Cart)
@trace_operation("update_cart_item")
async def update_cart_item(user_id: str, product_id: str, update: CartItemUpdate):
    """Update cart item quantity."""
    add_span_attribute("user_id", user_id)
    add_span_attribute("product_id", product_id)
    add_span_attribute("new_quantity", update.quantity)
    
    cart_data = await get_cart_data(user_id)
    items = cart_data["items"]
    
    if product_id not in items:
        raise HTTPException(status_code=404, detail="Item not in cart")
    
    if update.quantity == 0:
        # Remove item
        del items[product_id]
        track_custom_event(
            "cart_item_removed",
            properties={"user_id": user_id, "product_id": product_id}
        )
    else:
        # Update quantity
        items[product_id]["quantity"] = update.quantity
        track_custom_event(
            "cart_item_updated",
            properties={"user_id": user_id, "product_id": product_id},
            measurements={"quantity": update.quantity}
        )
    
    await save_cart_data(user_id, items)
    
    cart_data["items"] = items
    cart_data["updated_at"] = datetime.utcnow().isoformat()
    
    return build_cart_response(user_id, cart_data)


@app.delete("/api/v1/cart/{user_id}/items/{product_id}", response_model=Cart)
@trace_operation("remove_from_cart")
async def remove_from_cart(user_id: str, product_id: str):
    """Remove item from cart."""
    add_span_attribute("user_id", user_id)
    add_span_attribute("product_id", product_id)
    
    cart_data = await get_cart_data(user_id)
    items = cart_data["items"]
    
    if product_id not in items:
        raise HTTPException(status_code=404, detail="Item not in cart")
    
    del items[product_id]
    await save_cart_data(user_id, items)
    
    track_custom_event(
        "cart_item_removed",
        properties={"user_id": user_id, "product_id": product_id}
    )
    
    logger.info("Item removed from cart", user_id=user_id, product_id=product_id)
    
    cart_data["items"] = items
    cart_data["updated_at"] = datetime.utcnow().isoformat()
    
    return build_cart_response(user_id, cart_data)


@app.delete("/api/v1/cart/{user_id}", status_code=204)
@trace_operation("clear_cart")
async def clear_cart(user_id: str):
    """Clear user's cart."""
    add_span_attribute("user_id", user_id)
    
    await app.state.redis.delete(get_cart_key(user_id))
    
    track_custom_event(
        "cart_cleared",
        properties={"user_id": user_id}
    )
    
    logger.info("Cart cleared", user_id=user_id)


@app.get("/api/v1/cart/{user_id}/count")
@trace_operation("get_cart_count")
async def get_cart_count(user_id: str):
    """Get number of items in cart (for header badge)."""
    cart_data = await get_cart_data(user_id)
    count = sum(item["quantity"] for item in cart_data["items"].values())
    
    return {"user_id": user_id, "count": count}


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8004")),
        reload=os.getenv("ENV", "development") == "development"
    )
