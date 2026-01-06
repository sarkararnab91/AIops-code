# Session 5: Microservices Part 2 (Cart, Payment, Order, Notification)

## 📋 Session Details
- **Duration**: 1 hour
- **Week**: 1, Day 5 (Friday)
- **Prerequisites**: Sessions 1-4 completed
- **Deliverable**: Cart, Payment, Order, and Notification services running

---

## 🎯 Learning Objectives

By the end of this session, you will:
1. Build Cart Service with Redis caching
2. Build Payment Service with payment state machine
3. Build Order Service with Service Bus integration
4. Build Notification Service as message consumer

---

## 📚 Concepts

### Service Interactions

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SESSION 5 SERVICES                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│    User adds to cart         User checks out           Order placed         │
│          │                        │                         │               │
│          ▼                        ▼                         ▼               │
│    ┌──────────┐            ┌──────────┐              ┌──────────┐          │
│    │   Cart   │───────────▶│  Order   │──────────────│ Payment  │          │
│    │ Service  │            │ Service  │              │ Service  │          │
│    └────┬─────┘            └────┬─────┘              └──────────┘          │
│         │                       │                                           │
│         │                       │ (Service Bus)                             │
│         ▼                       ▼                                           │
│    ┌──────────┐            ┌──────────┐                                    │
│    │  Redis   │            │Notification                                   │
│    │  Cache   │            │ Service  │──────▶ Email/SMS                   │
│    └──────────┘            └──────────┘                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Message-Driven Architecture

Service Bus enables loose coupling:
- **Order Service** → publishes order events
- **Notification Service** → subscribes and sends notifications
- **Inventory Service** → subscribes and updates stock

---

## 🛠️ Hands-On Exercise

### Step 1: Create Cart Service

Create `ecommerce-app/services/cart-service/app/main.py`:

```python
"""Cart Service - Shopping cart management with Redis caching."""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from uuid import uuid4
import json

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import redis
import structlog
import jwt

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()


class Settings(BaseSettings):
    service_name: str = "cart-service"
    service_version: str = "1.0.0"
    redis_host: str
    redis_port: int = 6380
    redis_password: str
    redis_ssl: bool = True
    jwt_secret: str = "your-secret-key-change-in-production"
    cart_ttl_hours: int = 72  # Cart expires after 72 hours
    host: str = "0.0.0.0"
    port: int = 8004
    
    class Config:
        env_file = ".env"


settings = Settings()
security = HTTPBearer()


# Pydantic Models
class CartItem(BaseModel):
    product_id: str
    name: str
    price: float = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    image_url: Optional[str] = None

class AddToCartRequest(BaseModel):
    product_id: str
    name: str
    price: float = Field(..., gt=0)
    quantity: int = Field(1, gt=0)
    image_url: Optional[str] = None

class UpdateQuantityRequest(BaseModel):
    quantity: int = Field(..., ge=0)

class Cart(BaseModel):
    user_id: str
    items: list[CartItem] = []
    created_at: str
    updated_at: str
    
    @property
    def total_items(self) -> int:
        return sum(item.quantity for item in self.items)
    
    @property
    def subtotal(self) -> float:
        return sum(item.price * item.quantity for item in self.items)


# Redis client
class CartCache:
    def __init__(self):
        self.client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            ssl=settings.redis_ssl,
            ssl_cert_reqs=None,
            decode_responses=True
        )
        logger.info("redis_connected", host=settings.redis_host)
    
    def _cart_key(self, user_id: str) -> str:
        return f"cart:{user_id}"
    
    async def get_cart(self, user_id: str) -> Optional[dict]:
        data = self.client.get(self._cart_key(user_id))
        return json.loads(data) if data else None
    
    async def save_cart(self, cart: dict) -> None:
        key = self._cart_key(cart["user_id"])
        ttl = settings.cart_ttl_hours * 3600
        self.client.setex(key, ttl, json.dumps(cart))
    
    async def delete_cart(self, user_id: str) -> None:
        self.client.delete(self._cart_key(user_id))


cache: Optional[CartCache] = None

def get_cache() -> CartCache:
    global cache
    if cache is None:
        cache = CartCache()
    return cache


# Auth
def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    payload = decode_token(credentials.credentials)
    return payload["sub"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("cart_service_starting")
    yield
    logger.info("cart_service_stopping")


app = FastAPI(
    title="Cart Service",
    description="Shopping cart management with Redis",
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


@app.get("/api/v1/cart")
async def get_cart(user_id: str = Depends(get_current_user_id)):
    """Get the current user's cart."""
    logger.info("get_cart", user_id=user_id)
    
    cart_data = await get_cache().get_cart(user_id)
    
    if not cart_data:
        cart_data = {
            "user_id": user_id,
            "items": [],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
    
    cart = Cart(**cart_data)
    return {
        **cart_data,
        "total_items": cart.total_items,
        "subtotal": cart.subtotal
    }


@app.post("/api/v1/cart/items")
async def add_to_cart(
    request: AddToCartRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Add an item to the cart."""
    logger.info("add_to_cart", user_id=user_id, product_id=request.product_id)
    
    cache = get_cache()
    cart_data = await cache.get_cart(user_id)
    
    if not cart_data:
        cart_data = {
            "user_id": user_id,
            "items": [],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
    
    # Check if item already in cart
    for item in cart_data["items"]:
        if item["product_id"] == request.product_id:
            item["quantity"] += request.quantity
            item["price"] = request.price  # Update price
            break
    else:
        cart_data["items"].append({
            "product_id": request.product_id,
            "name": request.name,
            "price": request.price,
            "quantity": request.quantity,
            "image_url": request.image_url
        })
    
    cart_data["updated_at"] = datetime.utcnow().isoformat()
    await cache.save_cart(cart_data)
    
    cart = Cart(**cart_data)
    return {
        **cart_data,
        "total_items": cart.total_items,
        "subtotal": cart.subtotal
    }


@app.put("/api/v1/cart/items/{product_id}")
async def update_cart_item(
    product_id: str,
    request: UpdateQuantityRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Update item quantity in cart."""
    logger.info("update_cart_item", user_id=user_id, product_id=product_id)
    
    cache = get_cache()
    cart_data = await cache.get_cart(user_id)
    
    if not cart_data:
        raise HTTPException(status_code=404, detail="Cart not found")
    
    # Find and update or remove item
    if request.quantity == 0:
        cart_data["items"] = [
            item for item in cart_data["items"] 
            if item["product_id"] != product_id
        ]
    else:
        found = False
        for item in cart_data["items"]:
            if item["product_id"] == product_id:
                item["quantity"] = request.quantity
                found = True
                break
        if not found:
            raise HTTPException(status_code=404, detail="Item not in cart")
    
    cart_data["updated_at"] = datetime.utcnow().isoformat()
    await cache.save_cart(cart_data)
    
    cart = Cart(**cart_data)
    return {
        **cart_data,
        "total_items": cart.total_items,
        "subtotal": cart.subtotal
    }


@app.delete("/api/v1/cart/items/{product_id}")
async def remove_from_cart(
    product_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Remove an item from the cart."""
    logger.info("remove_from_cart", user_id=user_id, product_id=product_id)
    
    cache = get_cache()
    cart_data = await cache.get_cart(user_id)
    
    if not cart_data:
        raise HTTPException(status_code=404, detail="Cart not found")
    
    original_count = len(cart_data["items"])
    cart_data["items"] = [
        item for item in cart_data["items"] 
        if item["product_id"] != product_id
    ]
    
    if len(cart_data["items"]) == original_count:
        raise HTTPException(status_code=404, detail="Item not in cart")
    
    cart_data["updated_at"] = datetime.utcnow().isoformat()
    await cache.save_cart(cart_data)
    
    return {"message": "Item removed", "product_id": product_id}


@app.delete("/api/v1/cart")
async def clear_cart(user_id: str = Depends(get_current_user_id)):
    """Clear the entire cart."""
    logger.info("clear_cart", user_id=user_id)
    await get_cache().delete_cart(user_id)
    return {"message": "Cart cleared"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
```

### Step 2: Create Payment Service

Create `ecommerce-app/services/payment-service/app/main.py`:

```python
"""Payment Service - Payment processing with state machine."""

from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4
import asyncio
import random

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from azure.cosmos import CosmosClient, ContainerProxy
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()


class Settings(BaseSettings):
    service_name: str = "payment-service"
    service_version: str = "1.0.0"
    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database: str = "ecommerce"
    cosmos_container: str = "payments"
    host: str = "0.0.0.0"
    port: int = 8005
    
    class Config:
        env_file = ".env"


settings = Settings()


# Payment State Machine
class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class PaymentMethod(str, Enum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"


# Valid state transitions
VALID_TRANSITIONS = {
    PaymentStatus.PENDING: [PaymentStatus.PROCESSING, PaymentStatus.CANCELLED],
    PaymentStatus.PROCESSING: [PaymentStatus.AUTHORIZED, PaymentStatus.FAILED],
    PaymentStatus.AUTHORIZED: [PaymentStatus.CAPTURED, PaymentStatus.REFUNDED, PaymentStatus.CANCELLED],
    PaymentStatus.CAPTURED: [PaymentStatus.REFUNDED],
    PaymentStatus.FAILED: [PaymentStatus.PENDING],  # Allow retry
    PaymentStatus.REFUNDED: [],
    PaymentStatus.CANCELLED: [],
}


# Pydantic Models
class PaymentRequest(BaseModel):
    order_id: str
    user_id: str
    amount: float = Field(..., gt=0)
    currency: str = "USD"
    method: PaymentMethod
    card_last_four: Optional[str] = None

class PaymentResponse(BaseModel):
    id: str
    order_id: str
    user_id: str
    amount: float
    currency: str
    status: PaymentStatus
    method: PaymentMethod
    created_at: str
    updated_at: str
    transaction_id: Optional[str] = None
    failure_reason: Optional[str] = None


# Database
class PaymentDatabase:
    def __init__(self):
        self.client = CosmosClient(settings.cosmos_endpoint, settings.cosmos_key)
        self.database = self.client.get_database_client(settings.cosmos_database)
        # Create payments container if not exists
        try:
            self.container = self.database.create_container_if_not_exists(
                id=settings.cosmos_container,
                partition_key={"paths": ["/order_id"], "kind": "Hash"}
            )
        except:
            self.container = self.database.get_container_client(settings.cosmos_container)
    
    async def get_payment(self, payment_id: str, order_id: str) -> Optional[dict]:
        try:
            return self.container.read_item(item=payment_id, partition_key=order_id)
        except:
            return None
    
    async def get_payments_by_order(self, order_id: str) -> list[dict]:
        query = "SELECT * FROM c WHERE c.order_id = @order_id"
        return list(self.container.query_items(
            query=query,
            parameters=[{"name": "@order_id", "value": order_id}]
        ))
    
    async def save_payment(self, payment: dict) -> dict:
        return self.container.upsert_item(body=payment)


db: Optional[PaymentDatabase] = None

def get_db() -> PaymentDatabase:
    global db
    if db is None:
        db = PaymentDatabase()
    return db


# Mock payment gateway
async def process_with_gateway(payment: dict) -> tuple[bool, Optional[str], Optional[str]]:
    """Simulate payment gateway processing."""
    logger.info("gateway_processing", payment_id=payment["id"], amount=payment["amount"])
    
    # Simulate network latency
    await asyncio.sleep(random.uniform(0.5, 2.0))
    
    # Simulate different outcomes
    # 90% success rate for demo purposes
    if random.random() < 0.9:
        transaction_id = f"TXN-{uuid4().hex[:12].upper()}"
        return True, transaction_id, None
    else:
        failure_reasons = [
            "Insufficient funds",
            "Card declined",
            "Network timeout",
            "Invalid card number",
            "Expired card"
        ]
        return False, None, random.choice(failure_reasons)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("payment_service_starting")
    yield
    logger.info("payment_service_stopping")


app = FastAPI(
    title="Payment Service",
    description="Payment processing with state machine",
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


@app.post("/api/v1/payments", response_model=PaymentResponse)
async def create_payment(request: PaymentRequest):
    """Create a new payment (initiates payment processing)."""
    logger.info("create_payment", order_id=request.order_id, amount=request.amount)
    
    payment_id = str(uuid4())
    now = datetime.utcnow().isoformat()
    
    payment = {
        "id": payment_id,
        "order_id": request.order_id,
        "user_id": request.user_id,
        "amount": request.amount,
        "currency": request.currency,
        "method": request.method.value,
        "status": PaymentStatus.PENDING.value,
        "created_at": now,
        "updated_at": now,
        "card_last_four": request.card_last_four,
        "transaction_id": None,
        "failure_reason": None,
        "status_history": [
            {"status": PaymentStatus.PENDING.value, "timestamp": now}
        ]
    }
    
    db = get_db()
    created = await db.save_payment(payment)
    
    return PaymentResponse(**created)


@app.post("/api/v1/payments/{payment_id}/process")
async def process_payment(payment_id: str, order_id: str):
    """Process a pending payment."""
    logger.info("process_payment", payment_id=payment_id)
    
    db = get_db()
    payment = await db.get_payment(payment_id, order_id)
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    current_status = PaymentStatus(payment["status"])
    
    # Validate state transition
    if PaymentStatus.PROCESSING not in VALID_TRANSITIONS.get(current_status, []):
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot process payment in {current_status.value} status"
        )
    
    # Update to processing
    now = datetime.utcnow().isoformat()
    payment["status"] = PaymentStatus.PROCESSING.value
    payment["updated_at"] = now
    payment["status_history"].append({
        "status": PaymentStatus.PROCESSING.value, 
        "timestamp": now
    })
    await db.save_payment(payment)
    
    # Process with gateway
    success, transaction_id, failure_reason = await process_with_gateway(payment)
    
    now = datetime.utcnow().isoformat()
    if success:
        payment["status"] = PaymentStatus.AUTHORIZED.value
        payment["transaction_id"] = transaction_id
    else:
        payment["status"] = PaymentStatus.FAILED.value
        payment["failure_reason"] = failure_reason
    
    payment["updated_at"] = now
    payment["status_history"].append({
        "status": payment["status"],
        "timestamp": now,
        "details": transaction_id or failure_reason
    })
    
    updated = await db.save_payment(payment)
    
    logger.info("payment_processed", 
               payment_id=payment_id, 
               status=payment["status"],
               transaction_id=transaction_id)
    
    return PaymentResponse(**updated)


@app.post("/api/v1/payments/{payment_id}/capture")
async def capture_payment(payment_id: str, order_id: str):
    """Capture an authorized payment."""
    logger.info("capture_payment", payment_id=payment_id)
    
    db = get_db()
    payment = await db.get_payment(payment_id, order_id)
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    if payment["status"] != PaymentStatus.AUTHORIZED.value:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot capture payment in {payment['status']} status"
        )
    
    now = datetime.utcnow().isoformat()
    payment["status"] = PaymentStatus.CAPTURED.value
    payment["updated_at"] = now
    payment["status_history"].append({
        "status": PaymentStatus.CAPTURED.value,
        "timestamp": now
    })
    
    updated = await db.save_payment(payment)
    return PaymentResponse(**updated)


@app.post("/api/v1/payments/{payment_id}/refund")
async def refund_payment(payment_id: str, order_id: str):
    """Refund a captured payment."""
    logger.info("refund_payment", payment_id=payment_id)
    
    db = get_db()
    payment = await db.get_payment(payment_id, order_id)
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    if payment["status"] not in [PaymentStatus.AUTHORIZED.value, PaymentStatus.CAPTURED.value]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot refund payment in {payment['status']} status"
        )
    
    now = datetime.utcnow().isoformat()
    payment["status"] = PaymentStatus.REFUNDED.value
    payment["updated_at"] = now
    payment["refund_id"] = f"RFN-{uuid4().hex[:12].upper()}"
    payment["status_history"].append({
        "status": PaymentStatus.REFUNDED.value,
        "timestamp": now,
        "details": payment["refund_id"]
    })
    
    updated = await db.save_payment(payment)
    return PaymentResponse(**updated)


@app.get("/api/v1/payments/{payment_id}")
async def get_payment(payment_id: str, order_id: str):
    """Get payment details."""
    payment = await get_db().get_payment(payment_id, order_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return PaymentResponse(**payment)


@app.get("/api/v1/orders/{order_id}/payments")
async def get_order_payments(order_id: str):
    """Get all payments for an order."""
    payments = await get_db().get_payments_by_order(order_id)
    return {"payments": [PaymentResponse(**p) for p in payments], "count": len(payments)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
```

### Step 3: Create Order Service

Create `ecommerce-app/services/order-service/app/main.py`:

```python
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
```

### Step 4: Create Notification Service

Create `ecommerce-app/services/notification-service/app/main.py`:

```python
"""Notification Service - Async message consumer for notifications."""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
import asyncio
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings
from azure.servicebus import ServiceBusClient
from azure.servicebus.aio import ServiceBusClient as AsyncServiceBusClient
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()


class Settings(BaseSettings):
    service_name: str = "notification-service"
    service_version: str = "1.0.0"
    service_bus_connection_string: str
    notification_queue: str = "notification-queue"
    host: str = "0.0.0.0"
    port: int = 8007
    
    class Config:
        env_file = ".env"


settings = Settings()


# Notification handlers
class NotificationHandler:
    """Handles different notification types."""
    
    async def handle_order_created(self, data: dict):
        """Handle order created notification."""
        logger.info("sending_order_confirmation",
                   order_id=data.get("order_id"),
                   user_id=data.get("user_id"))
        
        # In production: Send email via SendGrid, Azure Communication Services, etc.
        # For demo: Just log
        print(f"""
        ╔════════════════════════════════════════════════╗
        ║           ORDER CONFIRMATION EMAIL              ║
        ╠════════════════════════════════════════════════╣
        ║  Order ID: {data.get('order_id'):<32} ║
        ║  Total: ${data.get('total', 0):<35.2f} ║
        ║  Items: {data.get('item_count', 0):<35} ║
        ║                                                ║
        ║  Thank you for your order!                     ║
        ╚════════════════════════════════════════════════╝
        """)
    
    async def handle_order_status_updated(self, data: dict):
        """Handle order status update notification."""
        logger.info("sending_status_update",
                   order_id=data.get("order_id"),
                   status=data.get("status"))
        
        status = data.get("status", "unknown")
        status_messages = {
            "confirmed": "Your order has been confirmed!",
            "processing": "Your order is being prepared.",
            "shipped": "Your order has been shipped!",
            "delivered": "Your order has been delivered.",
            "cancelled": "Your order has been cancelled.",
        }
        
        message = status_messages.get(status, f"Order status: {status}")
        
        print(f"""
        ╔════════════════════════════════════════════════╗
        ║            ORDER STATUS UPDATE                  ║
        ╠════════════════════════════════════════════════╣
        ║  Order ID: {data.get('order_id'):<32} ║
        ║  Status: {status:<34} ║
        ║                                                ║
        ║  {message:<45} ║
        ╚════════════════════════════════════════════════╝
        """)
    
    async def handle_payment_success(self, data: dict):
        """Handle payment success notification."""
        logger.info("sending_payment_confirmation",
                   order_id=data.get("order_id"),
                   amount=data.get("amount"))
        
        print(f"""
        ╔════════════════════════════════════════════════╗
        ║           PAYMENT CONFIRMATION                  ║
        ╠════════════════════════════════════════════════╣
        ║  Order ID: {data.get('order_id'):<32} ║
        ║  Amount: ${data.get('amount', 0):<34.2f} ║
        ║                                                ║
        ║  Payment processed successfully!               ║
        ╚════════════════════════════════════════════════╝
        """)
    
    async def handle(self, event_type: str, data: dict):
        """Route to appropriate handler."""
        handlers = {
            "order_created": self.handle_order_created,
            "order_status_updated": self.handle_order_status_updated,
            "payment_success": self.handle_payment_success,
        }
        
        handler = handlers.get(event_type)
        if handler:
            await handler(data)
        else:
            logger.warning("unknown_event_type", event_type=event_type)


handler = NotificationHandler()


# Message processor
class MessageProcessor:
    """Processes messages from Service Bus queue."""
    
    def __init__(self):
        self.client = ServiceBusClient.from_connection_string(
            settings.service_bus_connection_string
        )
        self.running = False
    
    async def start(self):
        """Start processing messages."""
        self.running = True
        logger.info("message_processor_starting", queue=settings.notification_queue)
        
        while self.running:
            try:
                with self.client.get_queue_receiver(
                    settings.notification_queue,
                    max_wait_time=5
                ) as receiver:
                    messages = receiver.receive_messages(max_message_count=10)
                    
                    for message in messages:
                        try:
                            body = json.loads(str(message))
                            event_type = body.get("event_type")
                            data = body.get("data", {})
                            
                            logger.info("processing_message", event_type=event_type)
                            await handler.handle(event_type, data)
                            
                            receiver.complete_message(message)
                            logger.info("message_completed", event_type=event_type)
                            
                        except Exception as e:
                            logger.error("message_processing_error", error=str(e))
                            receiver.abandon_message(message)
                
                await asyncio.sleep(1)  # Brief pause between polls
                
            except Exception as e:
                logger.error("receiver_error", error=str(e))
                await asyncio.sleep(5)  # Wait before retry
    
    def stop(self):
        """Stop processing messages."""
        self.running = False
        logger.info("message_processor_stopping")


processor: Optional[MessageProcessor] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global processor
    logger.info("notification_service_starting")
    
    # Start message processor in background
    processor = MessageProcessor()
    asyncio.create_task(processor.start())
    
    yield
    
    # Stop processor
    if processor:
        processor.stop()
    logger.info("notification_service_stopping")


app = FastAPI(
    title="Notification Service",
    description="Async notification processing",
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
    return {
        "status": "healthy",
        "service": settings.service_name,
        "processor_running": processor.running if processor else False
    }


@app.get("/api/v1/notifications/status")
async def processor_status():
    """Get message processor status."""
    return {
        "running": processor.running if processor else False,
        "queue": settings.notification_queue
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
```

### Step 5: Deploy to AKS

1. **Build Docker Images**

   Build the container images and push them to your Azure Container Registry:

   ```bash
   # Build Cart Service
   az acr build --registry aiopstrainacr --image cart-service:v1 ./services/cart-service

   # Build Payment Service
   az acr build --registry aiopstrainacr --image payment-service:v1 ./services/payment-service

   # Build Order Service
   az acr build --registry aiopstrainacr --image order-service:v1 ./services/order-service

   # Build Notification Service
   az acr build --registry aiopstrainacr --image notification-service:v1 ./services/notification-service
   ```

2. **Deploy to Kubernetes**

   Apply the deployment manifests to your AKS cluster:

   ```bash
   kubectl apply -f infrastructure/kubernetes/services/cart.yaml
   kubectl apply -f infrastructure/kubernetes/services/payment.yaml
   kubectl apply -f infrastructure/kubernetes/services/order.yaml
   kubectl apply -f infrastructure/kubernetes/services/notification.yaml
   ```

3. **Verify Deployment**

   Check that all pods are running:

   ```bash
   kubectl get pods
   ```

   You should see all four new services (cart, payment, order, notification) in the `Running` state.

---

## 🧪 Verification Checklist

Before moving to the next session, ensure you have:

- [ ] Cart Service with Redis caching
- [ ] Payment Service with state machine (pending → processing → authorized → captured)
- [ ] Order Service with Service Bus integration
- [ ] Notification Service consuming messages
- [ ] All services have health endpoints
- [ ] Inter-service communication working

---

## 📖 Key Takeaways

1. **Redis** is perfect for session/cart data with TTL
2. **State machines** prevent invalid payment transitions
3. **Service Bus** enables reliable async communication
4. **Background processors** handle notifications asynchronously

---

## 🔜 Next Session Preview

**Session 6: Vue.js Frontend & API Gateway**
- Build the e-commerce frontend
- Configure API gateway/ingress
- End-to-end user flow testing

---

## 📚 Additional Resources

- [Redis Python Client](https://redis-py.readthedocs.io/)
- [Azure Service Bus](https://docs.microsoft.com/en-us/azure/service-bus-messaging/)
- [State Machine Pattern](https://refactoring.guru/design-patterns/state)
