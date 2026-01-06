"""Order Service - Order management with Service Bus integration."""

from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from azure.cosmos import CosmosClient
from azure.servicebus import ServiceBusClient, ServiceBusMessage
import structlog
import jwt
import json

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()


class Settings(BaseSettings):
    service_name: str = "order-service"
    service_version: str = "1.0.0"
    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database: str = "ecommerce"
    cosmos_container: str = "orders"
    service_bus_connection_string: str
    notification_queue: str = "notification-queue"
    inventory_queue: str = "inventory-queue"
    jwt_secret: str = "your-secret-key-change-in-production"
    host: str = "0.0.0.0"
    port: int = 8006
    
    class Config:
        env_file = ".env"


settings = Settings()
security = HTTPBearer()


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class OrderItem(BaseModel):
    product_id: str
    name: str
    quantity: int = Field(..., gt=0)
    price: float = Field(..., gt=0)

class ShippingAddress(BaseModel):
    name: str
    street: str
    city: str
    state: str
    zip_code: str
    country: str = "USA"

class CreateOrderRequest(BaseModel):
    items: list[OrderItem]
    shipping_address: ShippingAddress
    payment_method: str = "credit_card"

class OrderResponse(BaseModel):
    id: str
    user_id: str
    status: OrderStatus
    items: list[OrderItem]
    subtotal: float
    tax: float
    shipping: float
    total: float
    shipping_address: ShippingAddress
    created_at: str
    updated_at: str


# Database
class OrderDatabase:
    def __init__(self):
        self.client = CosmosClient(settings.cosmos_endpoint, settings.cosmos_key)
        self.database = self.client.get_database_client(settings.cosmos_database)
        self.container = self.database.get_container_client(settings.cosmos_container)
    
    async def get_order(self, order_id: str, user_id: str) -> Optional[dict]:
        try:
            return self.container.read_item(item=order_id, partition_key=user_id)
        except:
            return None
    
    async def get_user_orders(self, user_id: str) -> list[dict]:
        query = "SELECT * FROM c WHERE c.user_id = @user_id ORDER BY c.created_at DESC"
        return list(self.container.query_items(
            query=query,
            parameters=[{"name": "@user_id", "value": user_id}]
        ))
    
    async def save_order(self, order: dict) -> dict:
        return self.container.upsert_item(body=order)


# Service Bus
class MessagePublisher:
    def __init__(self):
        self.client = ServiceBusClient.from_connection_string(
            settings.service_bus_connection_string
        )
    
    async def publish_notification(self, event_type: str, data: dict):
        """Publish notification event."""
        with self.client.get_queue_sender(settings.notification_queue) as sender:
            message = ServiceBusMessage(
                body=json.dumps({
                    "event_type": event_type,
                    "data": data,
                    "timestamp": datetime.utcnow().isoformat()
                }),
                content_type="application/json",
                application_properties={"event_type": event_type}
            )
            sender.send_messages(message)
            logger.info("notification_published", event_type=event_type)
    
    async def publish_inventory_update(self, order_id: str, items: list):
        """Publish inventory reservation request."""
        with self.client.get_queue_sender(settings.inventory_queue) as sender:
            message = ServiceBusMessage(
                body=json.dumps({
                    "event_type": "reserve_inventory",
                    "order_id": order_id,
                    "items": items,
                    "timestamp": datetime.utcnow().isoformat()
                }),
                content_type="application/json"
            )
            sender.send_messages(message)
            logger.info("inventory_update_published", order_id=order_id)


db: Optional[OrderDatabase] = None
publisher: Optional[MessagePublisher] = None


def get_db() -> OrderDatabase:
    global db
    if db is None:
        db = OrderDatabase()
    return db

def get_publisher() -> MessagePublisher:
    global publisher
    if publisher is None:
        publisher = MessagePublisher()
    return publisher


# Auth
async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
        return payload["sub"]
    except:
        raise HTTPException(status_code=401, detail="Invalid token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("order_service_starting")
    yield
    logger.info("order_service_stopping")


app = FastAPI(
    title="Order Service",
    description="Order management with async messaging",
    version=settings.service_version,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.service_name}


@app.post("/api/v1/orders", response_model=OrderResponse)
async def create_order(
    request: CreateOrderRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Create a new order."""
    logger.info("create_order", user_id=user_id, item_count=len(request.items))
    
    order_id = str(uuid4())
    now = datetime.utcnow().isoformat()
    
    # Calculate totals
    subtotal = sum(item.price * item.quantity for item in request.items)
    tax = round(subtotal * 0.08, 2)  # 8% tax
    shipping = 5.99 if subtotal < 50 else 0  # Free shipping over $50
    total = round(subtotal + tax + shipping, 2)
    
    order = {
        "id": order_id,
        "user_id": user_id,
        "status": OrderStatus.PENDING.value,
        "items": [item.dict() for item in request.items],
        "subtotal": subtotal,
        "tax": tax,
        "shipping": shipping,
        "total": total,
        "shipping_address": request.shipping_address.dict(),
        "payment_method": request.payment_method,
        "created_at": now,
        "updated_at": now,
        "status_history": [
            {"status": OrderStatus.PENDING.value, "timestamp": now}
        ]
    }
    
    # Save order
    db = get_db()
    created = await db.save_order(order)
    
    # Publish events
    try:
        pub = get_publisher()
        
        # Reserve inventory
        await pub.publish_inventory_update(
            order_id=order_id,
            items=[{"product_id": i.product_id, "quantity": i.quantity} for i in request.items]
        )
        
        # Send order confirmation notification
        await pub.publish_notification(
            event_type="order_created",
            data={
                "order_id": order_id,
                "user_id": user_id,
                "total": total,
                "item_count": len(request.items)
            }
        )
    except Exception as e:
        logger.error("failed_to_publish_events", error=str(e))
    
    return OrderResponse(**created)


@app.get("/api/v1/orders", response_model=list[OrderResponse])
async def list_orders(user_id: str = Depends(get_current_user_id)):
    """List all orders for the current user."""
    orders = await get_db().get_user_orders(user_id)
    return [OrderResponse(**o) for o in orders]


@app.get("/api/v1/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Get order details."""
    order = await get_db().get_order(order_id, user_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderResponse(**order)


@app.put("/api/v1/orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    new_status: OrderStatus,
    user_id: str = Depends(get_current_user_id)
):
    """Update order status."""
    logger.info("update_order_status", order_id=order_id, new_status=new_status.value)
    
    db = get_db()
    order = await db.get_order(order_id, user_id)
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    now = datetime.utcnow().isoformat()
    order["status"] = new_status.value
    order["updated_at"] = now
    order["status_history"].append({
        "status": new_status.value,
        "timestamp": now
    })
    
    updated = await db.save_order(order)
    
    # Send notification
    try:
        await get_publisher().publish_notification(
            event_type="order_status_updated",
            data={
                "order_id": order_id,
                "user_id": user_id,
                "status": new_status.value
            }
        )
    except Exception as e:
        logger.error("failed_to_publish_notification", error=str(e))
    
    return OrderResponse(**updated)


@app.post("/api/v1/orders/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Cancel an order."""
    logger.info("cancel_order", order_id=order_id)
    
    db = get_db()
    order = await db.get_order(order_id, user_id)
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order["status"] in [OrderStatus.SHIPPED.value, OrderStatus.DELIVERED.value]:
        raise HTTPException(status_code=400, detail="Cannot cancel shipped/delivered order")
    
    now = datetime.utcnow().isoformat()
    order["status"] = OrderStatus.CANCELLED.value
    order["updated_at"] = now
    order["status_history"].append({
        "status": OrderStatus.CANCELLED.value,
        "timestamp": now
    })
    
    updated = await db.save_order(order)
    
    return OrderResponse(**updated)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
