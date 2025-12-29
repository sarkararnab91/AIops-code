"""
Order Service - Order Management for E-Commerce
Handles order creation, processing, and status management.
"""

import os
import uuid
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
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
    add_span_event,
    track_custom_event,
    get_cosmos_client,
    get_redis_client,
    TelemetryLogger,
)


# Configuration
SERVICE_NAME = "order-service"
CONTAINER_NAME = "orders"

# Service URLs for inter-service communication
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8002")
CART_SERVICE_URL = os.getenv("CART_SERVICE_URL", "http://cart-service:8004")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8005")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8007")

# Initialize telemetry
configure_telemetry(SERVICE_NAME)
logger = TelemetryLogger(SERVICE_NAME)


# =============================================================================
# MODELS
# =============================================================================

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class OrderItem(BaseModel):
    """Order line item."""
    product_id: str
    product_name: str
    quantity: int = Field(..., ge=1)
    unit_price: float = Field(..., gt=0)
    total_price: float


class ShippingAddress(BaseModel):
    """Shipping address."""
    full_name: str
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str = "US"
    phone: Optional[str] = None


class OrderCreate(BaseModel):
    """Request model for creating an order."""
    user_id: str
    items: List[OrderItem]
    shipping_address: ShippingAddress
    payment_method: str = Field(default="credit_card")
    notes: Optional[str] = None


class OrderUpdate(BaseModel):
    """Request model for updating an order."""
    status: Optional[OrderStatus] = None
    tracking_number: Optional[str] = None
    notes: Optional[str] = None


class Order(BaseModel):
    """Order model."""
    id: str
    user_id: str
    items: List[OrderItem]
    subtotal: float
    tax: float
    shipping_cost: float
    total: float
    status: OrderStatus
    shipping_address: ShippingAddress
    payment_method: str
    payment_id: Optional[str] = None
    tracking_number: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    updated_at: str


class OrderList(BaseModel):
    """Response model for order list."""
    items: List[Order]
    total: int
    page: int
    page_size: int


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
    logger.info("Starting Order Service")
    
    cosmos = await get_cosmos_client()
    redis = await get_redis_client()
    
    app.state.cosmos = cosmos
    app.state.redis = redis
    
    # Initialize HTTP clients for other services
    app.state.inventory_client = TracingHTTPClient(INVENTORY_SERVICE_URL, SERVICE_NAME)
    app.state.cart_client = TracingHTTPClient(CART_SERVICE_URL, SERVICE_NAME)
    app.state.payment_client = TracingHTTPClient(PAYMENT_SERVICE_URL, SERVICE_NAME)
    app.state.notification_client = TracingHTTPClient(NOTIFICATION_SERVICE_URL, SERVICE_NAME)
    
    logger.info("Order Service started successfully")
    yield
    
    await cosmos.close()
    await redis.close()


app = FastAPI(
    title="Order Service",
    description="Order management for e-commerce platform",
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

def calculate_tax(subtotal: float, state: str) -> float:
    """Calculate tax based on state."""
    tax_rates = {
        "CA": 0.0725,
        "NY": 0.08,
        "TX": 0.0625,
        "FL": 0.06,
    }
    rate = tax_rates.get(state.upper(), 0.05)
    return round(subtotal * rate, 2)


def calculate_shipping(item_count: int, total_weight: float = 0) -> float:
    """Calculate shipping cost."""
    base_cost = 5.99
    per_item = 0.99
    return round(base_cost + (item_count * per_item), 2)


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


@app.post("/api/v1/orders", response_model=Order, status_code=201)
@trace_operation("create_order")
async def create_order(order: OrderCreate, background_tasks: BackgroundTasks):
    """Create a new order."""
    order_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    add_span_attribute("order.id", order_id)
    add_span_attribute("order.user_id", order.user_id)
    add_span_attribute("order.item_count", len(order.items))
    
    add_span_event("order_creation_started")
    
    # Calculate totals
    subtotal = sum(item.total_price for item in order.items)
    tax = calculate_tax(subtotal, order.shipping_address.state)
    shipping_cost = calculate_shipping(len(order.items))
    total = round(subtotal + tax + shipping_cost, 2)
    
    add_span_attribute("order.subtotal", subtotal)
    add_span_attribute("order.total", total)
    
    # Step 1: Reserve inventory
    add_span_event("reserving_inventory")
    for item in order.items:
        try:
            response = await app.state.inventory_client.post(
                "/api/v1/inventory/reserve",
                json={
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "order_id": order_id
                }
            )
            if response["status_code"] != 200:
                add_span_event("inventory_reservation_failed", {
                    "product_id": item.product_id
                })
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient inventory for {item.product_name}"
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to reserve inventory", error=str(e))
            # Continue with order for training (in production, would fail)
    
    add_span_event("inventory_reserved")
    
    # Step 2: Create order document
    order_data = {
        "id": order_id,
        "user_id": order.user_id,
        "userId": order.user_id,  # Partition key
        "items": [item.model_dump() for item in order.items],
        "subtotal": subtotal,
        "tax": tax,
        "shipping_cost": shipping_cost,
        "total": total,
        "status": OrderStatus.PENDING.value,
        "shipping_address": order.shipping_address.model_dump(),
        "payment_method": order.payment_method,
        "payment_id": None,
        "tracking_number": None,
        "notes": order.notes,
        "created_at": now,
        "updated_at": now,
    }
    
    await app.state.cosmos.create_item(CONTAINER_NAME, order_data)
    
    add_span_event("order_created")
    
    # Step 3: Create payment (async)
    add_span_event("initiating_payment")
    try:
        payment_response = await app.state.payment_client.post(
            "/api/v1/payments",
            json={
                "order_id": order_id,
                "user_id": order.user_id,
                "amount": total,
                "method": order.payment_method
            }
        )
        
        if payment_response["status_code"] == 201:
            payment_id = payment_response["data"]["id"]
            
            # Update order with payment ID
            await app.state.cosmos.update_item(
                CONTAINER_NAME,
                order_id,
                order.user_id,
                {
                    "payment_id": payment_id,
                    "status": OrderStatus.PAYMENT_PENDING.value,
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
            order_data["payment_id"] = payment_id
            order_data["status"] = OrderStatus.PAYMENT_PENDING.value
    except Exception as e:
        logger.warning("Payment creation failed, order still created", error=str(e))
    
    # Step 4: Clear cart (background)
    async def clear_cart():
        try:
            await app.state.cart_client.delete(f"/api/v1/cart/{order.user_id}")
        except Exception as e:
            logger.warning("Failed to clear cart", error=str(e))
    
    background_tasks.add_task(clear_cart)
    
    # Track business event
    track_custom_event(
        "order_created",
        properties={
            "order_id": order_id,
            "user_id": order.user_id,
            "item_count": len(order.items),
            "payment_method": order.payment_method
        },
        measurements={
            "subtotal": subtotal,
            "tax": tax,
            "shipping": shipping_cost,
            "total": total
        }
    )
    
    logger.info(
        "Order created successfully",
        order_id=order_id,
        user_id=order.user_id,
        total=total
    )
    
    return Order(**order_data)


@app.get("/api/v1/orders/{order_id}", response_model=Order)
@trace_operation("get_order")
async def get_order(order_id: str, user_id: str = Query(...)):
    """Get an order by ID."""
    add_span_attribute("order.id", order_id)
    
    query = "SELECT * FROM c WHERE c.id = @id AND c.userId = @user_id"
    parameters = [
        {"name": "@id", "value": order_id},
        {"name": "@user_id", "value": user_id}
    ]
    
    items = await app.state.cosmos.query_items(CONTAINER_NAME, query, parameters)
    
    if not items:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return Order(**items[0])


@app.get("/api/v1/orders", response_model=OrderList)
@trace_operation("list_orders")
async def list_orders(
    user_id: str = Query(...),
    status: Optional[OrderStatus] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """List orders for a user."""
    add_span_attribute("user_id", user_id)
    
    conditions = ["c.userId = @user_id"]
    parameters = [{"name": "@user_id", "value": user_id}]
    
    if status:
        conditions.append("c.status = @status")
        parameters.append({"name": "@status", "value": status.value})
    
    where_clause = " AND ".join(conditions)
    offset = (page - 1) * page_size
    
    # Count query
    count_query = f"SELECT VALUE COUNT(1) FROM c WHERE {where_clause}"
    count_result = await app.state.cosmos.query_items(CONTAINER_NAME, count_query, parameters)
    total = count_result[0] if count_result else 0
    
    # Data query
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
    
    items = await app.state.cosmos.query_items(CONTAINER_NAME, data_query, parameters)
    
    return OrderList(
        items=[Order(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size
    )


@app.put("/api/v1/orders/{order_id}/status", response_model=Order)
@trace_operation("update_order_status")
async def update_order_status(
    order_id: str,
    user_id: str = Query(...),
    updates: OrderUpdate = None
):
    """Update order status."""
    add_span_attribute("order.id", order_id)
    add_span_attribute("order.new_status", updates.status.value if updates.status else None)
    
    # Get current order
    current = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT * FROM c WHERE c.id = @id AND c.userId = @user_id",
        [
            {"name": "@id", "value": order_id},
            {"name": "@user_id", "value": user_id}
        ]
    )
    
    if not current:
        raise HTTPException(status_code=404, detail="Order not found")
    
    old_status = current[0]["status"]
    
    # Build updates
    update_data = {}
    if updates.status:
        update_data["status"] = updates.status.value
    if updates.tracking_number:
        update_data["tracking_number"] = updates.tracking_number
    if updates.notes:
        update_data["notes"] = updates.notes
    
    update_data["updated_at"] = datetime.utcnow().isoformat()
    
    result = await app.state.cosmos.update_item(
        CONTAINER_NAME,
        order_id,
        user_id,
        update_data
    )
    
    # Track status change
    track_custom_event(
        "order_status_changed",
        properties={
            "order_id": order_id,
            "old_status": old_status,
            "new_status": updates.status.value if updates.status else old_status
        }
    )
    
    # Send notification if status changed to shipped/delivered
    if updates.status in [OrderStatus.SHIPPED, OrderStatus.DELIVERED]:
        try:
            await app.state.notification_client.post(
                "/api/v1/notifications",
                json={
                    "user_id": user_id,
                    "type": "order_update",
                    "title": f"Order {updates.status.value}",
                    "message": f"Your order {order_id} has been {updates.status.value}.",
                    "metadata": {"order_id": order_id, "status": updates.status.value}
                }
            )
        except Exception as e:
            logger.warning("Failed to send notification", error=str(e))
    
    logger.info(
        "Order status updated",
        order_id=order_id,
        old_status=old_status,
        new_status=updates.status.value if updates.status else old_status
    )
    
    return Order(**result)


@app.post("/api/v1/orders/{order_id}/cancel", response_model=Order)
@trace_operation("cancel_order")
async def cancel_order(order_id: str, user_id: str = Query(...)):
    """Cancel an order."""
    add_span_attribute("order.id", order_id)
    
    # Get order
    current = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT * FROM c WHERE c.id = @id AND c.userId = @user_id",
        [
            {"name": "@id", "value": order_id},
            {"name": "@user_id", "value": user_id}
        ]
    )
    
    if not current:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = current[0]
    
    # Check if cancellable
    non_cancellable = [OrderStatus.SHIPPED.value, OrderStatus.DELIVERED.value, OrderStatus.CANCELLED.value]
    if order["status"] in non_cancellable:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel order in {order['status']} status"
        )
    
    # Release inventory
    add_span_event("releasing_inventory")
    for item in order["items"]:
        try:
            await app.state.inventory_client.post(
                "/api/v1/inventory/release",
                json={
                    "product_id": item["product_id"],
                    "quantity": item["quantity"],
                    "order_id": order_id
                }
            )
        except Exception as e:
            logger.warning("Failed to release inventory", product_id=item["product_id"], error=str(e))
    
    # Update status
    result = await app.state.cosmos.update_item(
        CONTAINER_NAME,
        order_id,
        user_id,
        {
            "status": OrderStatus.CANCELLED.value,
            "updated_at": datetime.utcnow().isoformat()
        }
    )
    
    track_custom_event(
        "order_cancelled",
        properties={"order_id": order_id, "user_id": user_id},
        measurements={"total": order["total"]}
    )
    
    logger.info("Order cancelled", order_id=order_id)
    
    return Order(**result)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8003")),
        reload=os.getenv("ENV", "development") == "development"
    )
