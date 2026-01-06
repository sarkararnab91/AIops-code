"""
Inventory Service - Stock Management
Handles inventory tracking, reservations, and stock updates.
"""

import os
import uuid
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI, HTTPException, Query
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
    add_span_event,
    track_custom_event,
    get_cosmos_client,
    get_redis_client,
    TelemetryLogger,
)


# Configuration
SERVICE_NAME = "inventory-service"
CONTAINER_NAME = "inventory"
CACHE_TTL = 60  # 1 minute for stock levels

# Initialize telemetry
configure_telemetry(SERVICE_NAME)
logger = TelemetryLogger(SERVICE_NAME)


# =============================================================================
# MODELS
# =============================================================================

class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    RELEASED = "released"
    EXPIRED = "expired"


class InventoryItem(BaseModel):
    """Inventory item model."""
    product_id: str
    sku: str
    quantity_available: int
    quantity_reserved: int
    reorder_level: int
    reorder_quantity: int
    warehouse_location: Optional[str] = None
    last_restocked: Optional[str] = None
    updated_at: str


class InventoryUpdate(BaseModel):
    """Request model for updating inventory."""
    quantity_adjustment: int  # Positive to add, negative to subtract
    reason: str = Field(..., min_length=1)


class ReservationRequest(BaseModel):
    """Request model for reserving inventory."""
    product_id: str
    quantity: int = Field(..., ge=1)
    order_id: str


class ReleaseRequest(BaseModel):
    """Request model for releasing reserved inventory."""
    product_id: str
    quantity: int = Field(..., ge=1)
    order_id: str


class StockCheck(BaseModel):
    """Stock check response."""
    product_id: str
    available: int
    reserved: int
    in_stock: bool
    low_stock: bool


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
    logger.info("Starting Inventory Service")
    
    cosmos = await get_cosmos_client()
    redis = await get_redis_client()
    
    app.state.cosmos = cosmos
    app.state.redis = redis
    
    logger.info("Inventory Service started successfully")
    yield
    
    await cosmos.close()
    await redis.close()


app = FastAPI(
    title="Inventory Service",
    description="Stock management and inventory tracking",
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

def get_stock_cache_key(product_id: str) -> str:
    """Generate cache key for stock level."""
    return f"stock:{product_id}"


async def get_inventory_item(product_id: str) -> Optional[dict]:
    """Get inventory item from database."""
    items = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT * FROM c WHERE c.productId = @product_id",
        [{"name": "@product_id", "value": product_id}]
    )
    return items[0] if items else None


async def update_stock_cache(product_id: str, available: int, reserved: int):
    """Update stock level in cache."""
    import json
    cache_key = get_stock_cache_key(product_id)
    await app.state.redis.set(
        cache_key,
        json.dumps({"available": available, "reserved": reserved}),
        ttl_seconds=CACHE_TTL
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


@app.get("/api/v1/inventory/{product_id}", response_model=StockCheck)
@trace_operation("check_stock")
async def check_stock(product_id: str):
    """Check stock level for a product."""
    add_span_attribute("product_id", product_id)
    
    # Try cache first
    import json
    cache_key = get_stock_cache_key(product_id)
    cached = await app.state.redis.get(cache_key)
    
    if cached:
        data = json.loads(cached)
        add_span_attribute("cache.hit", True)
        
        return StockCheck(
            product_id=product_id,
            available=data["available"],
            reserved=data["reserved"],
            in_stock=data["available"] > 0,
            low_stock=data["available"] < 10
        )
    
    add_span_attribute("cache.hit", False)
    
    item = await get_inventory_item(product_id)
    
    if not item:
        raise HTTPException(status_code=404, detail="Product not found in inventory")
    
    available = item["quantity_available"]
    reserved = item["quantity_reserved"]
    
    # Update cache
    await update_stock_cache(product_id, available, reserved)
    
    return StockCheck(
        product_id=product_id,
        available=available,
        reserved=reserved,
        in_stock=available > 0,
        low_stock=available < item.get("reorder_level", 10)
    )


@app.post("/api/v1/inventory/reserve", response_model=dict)
@trace_operation("reserve_inventory")
async def reserve_inventory(request: ReservationRequest):
    """Reserve inventory for an order."""
    add_span_attribute("product_id", request.product_id)
    add_span_attribute("order_id", request.order_id)
    add_span_attribute("quantity", request.quantity)
    
    add_span_event("checking_availability")
    
    item = await get_inventory_item(request.product_id)
    
    if not item:
        raise HTTPException(status_code=404, detail="Product not found")
    
    available = item["quantity_available"]
    
    if available < request.quantity:
        add_span_event("insufficient_stock", {
            "available": available,
            "requested": request.quantity
        })
        
        track_custom_event(
            "inventory_reservation_failed",
            properties={
                "product_id": request.product_id,
                "order_id": request.order_id,
                "reason": "insufficient_stock"
            },
            measurements={
                "available": available,
                "requested": request.quantity
            }
        )
        
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient stock. Available: {available}, Requested: {request.quantity}"
        )
    
    # Update inventory
    new_available = available - request.quantity
    new_reserved = item["quantity_reserved"] + request.quantity
    
    await app.state.cosmos.update_item(
        CONTAINER_NAME,
        item["id"],
        request.product_id,
        {
            "quantity_available": new_available,
            "quantity_reserved": new_reserved,
            "updated_at": datetime.utcnow().isoformat()
        }
    )
    
    # Update cache
    await update_stock_cache(request.product_id, new_available, new_reserved)
    
    # Store reservation
    reservation_id = str(uuid.uuid4())
    reservation_key = f"reservation:{request.order_id}:{request.product_id}"
    import json
    await app.state.redis.set(
        reservation_key,
        json.dumps({
            "id": reservation_id,
            "product_id": request.product_id,
            "quantity": request.quantity,
            "order_id": request.order_id,
            "status": ReservationStatus.PENDING.value,
            "created_at": datetime.utcnow().isoformat()
        }),
        ttl_seconds=3600  # 1 hour expiry
    )
    
    add_span_event("inventory_reserved")
    
    track_custom_event(
        "inventory_reserved",
        properties={
            "product_id": request.product_id,
            "order_id": request.order_id,
            "reservation_id": reservation_id
        },
        measurements={"quantity": request.quantity}
    )
    
    logger.info(
        "Inventory reserved",
        product_id=request.product_id,
        order_id=request.order_id,
        quantity=request.quantity
    )
    
    return {
        "reservation_id": reservation_id,
        "product_id": request.product_id,
        "quantity_reserved": request.quantity,
        "available_after": new_available
    }


@app.post("/api/v1/inventory/release", response_model=dict)
@trace_operation("release_inventory")
async def release_inventory(request: ReleaseRequest):
    """Release reserved inventory (for cancelled orders)."""
    add_span_attribute("product_id", request.product_id)
    add_span_attribute("order_id", request.order_id)
    add_span_attribute("quantity", request.quantity)
    
    item = await get_inventory_item(request.product_id)
    
    if not item:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Update inventory
    new_available = item["quantity_available"] + request.quantity
    new_reserved = max(0, item["quantity_reserved"] - request.quantity)
    
    await app.state.cosmos.update_item(
        CONTAINER_NAME,
        item["id"],
        request.product_id,
        {
            "quantity_available": new_available,
            "quantity_reserved": new_reserved,
            "updated_at": datetime.utcnow().isoformat()
        }
    )
    
    # Update cache
    await update_stock_cache(request.product_id, new_available, new_reserved)
    
    # Remove reservation
    reservation_key = f"reservation:{request.order_id}:{request.product_id}"
    await app.state.redis.delete(reservation_key)
    
    track_custom_event(
        "inventory_released",
        properties={
            "product_id": request.product_id,
            "order_id": request.order_id
        },
        measurements={"quantity": request.quantity}
    )
    
    logger.info(
        "Inventory released",
        product_id=request.product_id,
        order_id=request.order_id,
        quantity=request.quantity
    )
    
    return {
        "product_id": request.product_id,
        "quantity_released": request.quantity,
        "available_after": new_available
    }


@app.post("/api/v1/inventory/confirm", response_model=dict)
@trace_operation("confirm_reservation")
async def confirm_reservation(order_id: str, product_id: str):
    """Confirm reservation after successful payment."""
    add_span_attribute("order_id", order_id)
    add_span_attribute("product_id", product_id)
    
    # Get reservation
    import json
    reservation_key = f"reservation:{order_id}:{product_id}"
    reservation_data = await app.state.redis.get(reservation_key)
    
    if not reservation_data:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    reservation = json.loads(reservation_data)
    
    # Update reservation status
    reservation["status"] = ReservationStatus.CONFIRMED.value
    await app.state.redis.set(reservation_key, json.dumps(reservation), ttl_seconds=86400)
    
    # Update inventory - move from reserved to sold (reduce reserved)
    item = await get_inventory_item(product_id)
    if item:
        new_reserved = max(0, item["quantity_reserved"] - reservation["quantity"])
        await app.state.cosmos.update_item(
            CONTAINER_NAME,
            item["id"],
            product_id,
            {
                "quantity_reserved": new_reserved,
                "updated_at": datetime.utcnow().isoformat()
            }
        )
    
    track_custom_event(
        "reservation_confirmed",
        properties={"order_id": order_id, "product_id": product_id},
        measurements={"quantity": reservation["quantity"]}
    )
    
    return {"status": "confirmed", "order_id": order_id, "product_id": product_id}


@app.put("/api/v1/inventory/{product_id}", response_model=InventoryItem)
@trace_operation("update_inventory")
async def update_inventory(product_id: str, update: InventoryUpdate):
    """Manually adjust inventory (restock or adjust)."""
    add_span_attribute("product_id", product_id)
    add_span_attribute("adjustment", update.quantity_adjustment)
    
    item = await get_inventory_item(product_id)
    
    if not item:
        raise HTTPException(status_code=404, detail="Product not found")
    
    new_quantity = item["quantity_available"] + update.quantity_adjustment
    
    if new_quantity < 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot reduce below zero"
        )
    
    now = datetime.utcnow().isoformat()
    updates = {
        "quantity_available": new_quantity,
        "updated_at": now
    }
    
    if update.quantity_adjustment > 0:
        updates["last_restocked"] = now
    
    result = await app.state.cosmos.update_item(
        CONTAINER_NAME,
        item["id"],
        product_id,
        updates
    )
    
    # Update cache
    await update_stock_cache(product_id, new_quantity, item["quantity_reserved"])
    
    track_custom_event(
        "inventory_adjusted",
        properties={
            "product_id": product_id,
            "reason": update.reason
        },
        measurements={
            "adjustment": update.quantity_adjustment,
            "new_quantity": new_quantity
        }
    )
    
    logger.info(
        "Inventory adjusted",
        product_id=product_id,
        adjustment=update.quantity_adjustment,
        reason=update.reason
    )
    
    return InventoryItem(
        product_id=product_id,
        sku=result.get("sku", ""),
        quantity_available=new_quantity,
        quantity_reserved=result["quantity_reserved"],
        reorder_level=result.get("reorder_level", 10),
        reorder_quantity=result.get("reorder_quantity", 50),
        warehouse_location=result.get("warehouse_location"),
        last_restocked=result.get("last_restocked"),
        updated_at=result["updated_at"]
    )


@app.get("/api/v1/inventory/low-stock", response_model=List[StockCheck])
@trace_operation("get_low_stock")
async def get_low_stock():
    """Get products with low stock levels."""
    
    items = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT * FROM c WHERE c.quantity_available <= c.reorder_level"
    )
    
    low_stock_items = [
        StockCheck(
            product_id=item["productId"],
            available=item["quantity_available"],
            reserved=item["quantity_reserved"],
            in_stock=item["quantity_available"] > 0,
            low_stock=True
        )
        for item in items
    ]
    
    track_custom_event(
        "low_stock_check",
        measurements={"count": len(low_stock_items)}
    )
    
    return low_stock_items


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8002")),
        reload=os.getenv("ENV", "development") == "development"
    )
