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
