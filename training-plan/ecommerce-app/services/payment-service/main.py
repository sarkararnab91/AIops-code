"""
Payment Service - Payment Processing
Handles payment creation, processing, and refunds.
"""

import os
import uuid
import random
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
    TelemetryLogger,
)


# Configuration
SERVICE_NAME = "payment-service"
CONTAINER_NAME = "payments"

# Initialize telemetry
configure_telemetry(SERVICE_NAME)
logger = TelemetryLogger(SERVICE_NAME)


# =============================================================================
# MODELS
# =============================================================================

class PaymentStatus(str, Enum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class PaymentMethod(str, Enum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"
    APPLE_PAY = "apple_pay"
    GOOGLE_PAY = "google_pay"


class PaymentCreate(BaseModel):
    """Request model for creating a payment."""
    order_id: str
    user_id: str
    amount: float = Field(..., gt=0)
    currency: str = Field(default="USD")
    method: PaymentMethod = PaymentMethod.CREDIT_CARD
    card_last_four: Optional[str] = Field(None, pattern="^[0-9]{4}$")


class PaymentRefund(BaseModel):
    """Request model for refunding a payment."""
    amount: float = Field(..., gt=0)
    reason: str = Field(..., min_length=1)


class Payment(BaseModel):
    """Payment model."""
    id: str
    order_id: str
    user_id: str
    amount: float
    currency: str
    method: PaymentMethod
    status: PaymentStatus
    card_last_four: Optional[str] = None
    transaction_id: Optional[str] = None
    failure_reason: Optional[str] = None
    refunded_amount: float = 0
    created_at: str
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
    logger.info("Starting Payment Service")
    
    cosmos = await get_cosmos_client()
    app.state.cosmos = cosmos
    
    logger.info("Payment Service started successfully")
    yield
    
    await cosmos.close()


app = FastAPI(
    title="Payment Service",
    description="Payment processing for e-commerce platform",
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
# PAYMENT SIMULATION
# =============================================================================

def simulate_payment_processing(amount: float, method: PaymentMethod) -> tuple:
    """
    Simulate payment processing with realistic failure scenarios.
    Returns (success, transaction_id, failure_reason)
    """
    import time
    
    # Simulate processing time (50-200ms)
    time.sleep(random.uniform(0.05, 0.2))
    
    # Simulate different failure scenarios
    failure_rate = 0.05  # 5% failure rate
    
    if random.random() < failure_rate:
        failure_reasons = [
            "Card declined - insufficient funds",
            "Card expired",
            "Invalid card number",
            "Transaction timeout",
            "Fraud detection triggered",
            "Card blocked by issuer"
        ]
        return False, None, random.choice(failure_reasons)
    
    # Success
    transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
    return True, transaction_id, None


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


@app.post("/api/v1/payments", response_model=Payment, status_code=201)
@trace_operation("create_payment")
async def create_payment(payment: PaymentCreate):
    """Create a new payment."""
    payment_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    add_span_attribute("payment.id", payment_id)
    add_span_attribute("payment.order_id", payment.order_id)
    add_span_attribute("payment.amount", payment.amount)
    add_span_attribute("payment.method", payment.method.value)
    
    payment_data = {
        "id": payment_id,
        "orderId": payment.order_id,  # Partition key
        "order_id": payment.order_id,
        "user_id": payment.user_id,
        "amount": payment.amount,
        "currency": payment.currency,
        "method": payment.method.value,
        "status": PaymentStatus.PENDING.value,
        "card_last_four": payment.card_last_four,
        "transaction_id": None,
        "failure_reason": None,
        "refunded_amount": 0,
        "created_at": now,
        "updated_at": now,
    }
    
    await app.state.cosmos.create_item(CONTAINER_NAME, payment_data)
    
    track_custom_event(
        "payment_created",
        properties={
            "payment_id": payment_id,
            "order_id": payment.order_id,
            "method": payment.method.value
        },
        measurements={"amount": payment.amount}
    )
    
    logger.info(
        "Payment created",
        payment_id=payment_id,
        order_id=payment.order_id,
        amount=payment.amount
    )
    
    return Payment(**payment_data)


@app.post("/api/v1/payments/{payment_id}/process", response_model=Payment)
@trace_operation("process_payment")
async def process_payment(payment_id: str, order_id: str = Query(...)):
    """Process a pending payment."""
    add_span_attribute("payment.id", payment_id)
    add_span_attribute("order_id", order_id)
    
    add_span_event("fetching_payment")
    
    # Get payment
    items = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT * FROM c WHERE c.id = @id AND c.orderId = @order_id",
        [
            {"name": "@id", "value": payment_id},
            {"name": "@order_id", "value": order_id}
        ]
    )
    
    if not items:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    payment = items[0]
    
    if payment["status"] != PaymentStatus.PENDING.value:
        raise HTTPException(
            status_code=400,
            detail=f"Payment is in {payment['status']} status, cannot process"
        )
    
    add_span_event("processing_payment")
    
    # Simulate payment processing
    success, transaction_id, failure_reason = simulate_payment_processing(
        payment["amount"],
        PaymentMethod(payment["method"])
    )
    
    add_span_attribute("payment.success", success)
    
    if success:
        updates = {
            "status": PaymentStatus.AUTHORIZED.value,
            "transaction_id": transaction_id,
            "updated_at": datetime.utcnow().isoformat()
        }
        add_span_event("payment_authorized", {"transaction_id": transaction_id})
        
        track_custom_event(
            "payment_authorized",
            properties={
                "payment_id": payment_id,
                "order_id": order_id,
                "transaction_id": transaction_id
            },
            measurements={"amount": payment["amount"]}
        )
    else:
        updates = {
            "status": PaymentStatus.FAILED.value,
            "failure_reason": failure_reason,
            "updated_at": datetime.utcnow().isoformat()
        }
        add_span_event("payment_failed", {"reason": failure_reason})
        
        track_custom_event(
            "payment_failed",
            properties={
                "payment_id": payment_id,
                "order_id": order_id,
                "reason": failure_reason
            },
            measurements={"amount": payment["amount"]}
        )
    
    result = await app.state.cosmos.update_item(
        CONTAINER_NAME,
        payment_id,
        order_id,
        updates
    )
    
    logger.info(
        "Payment processed",
        payment_id=payment_id,
        success=success,
        transaction_id=transaction_id if success else None
    )
    
    return Payment(**result)


@app.post("/api/v1/payments/{payment_id}/capture", response_model=Payment)
@trace_operation("capture_payment")
async def capture_payment(payment_id: str, order_id: str = Query(...)):
    """Capture an authorized payment."""
    add_span_attribute("payment.id", payment_id)
    
    items = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT * FROM c WHERE c.id = @id AND c.orderId = @order_id",
        [
            {"name": "@id", "value": payment_id},
            {"name": "@order_id", "value": order_id}
        ]
    )
    
    if not items:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    payment = items[0]
    
    if payment["status"] != PaymentStatus.AUTHORIZED.value:
        raise HTTPException(
            status_code=400,
            detail="Payment must be in authorized status to capture"
        )
    
    result = await app.state.cosmos.update_item(
        CONTAINER_NAME,
        payment_id,
        order_id,
        {
            "status": PaymentStatus.CAPTURED.value,
            "updated_at": datetime.utcnow().isoformat()
        }
    )
    
    track_custom_event(
        "payment_captured",
        properties={"payment_id": payment_id, "order_id": order_id},
        measurements={"amount": payment["amount"]}
    )
    
    logger.info("Payment captured", payment_id=payment_id)
    
    return Payment(**result)


@app.post("/api/v1/payments/{payment_id}/refund", response_model=Payment)
@trace_operation("refund_payment")
async def refund_payment(payment_id: str, order_id: str = Query(...), refund: PaymentRefund = None):
    """Refund a captured payment."""
    add_span_attribute("payment.id", payment_id)
    add_span_attribute("refund.amount", refund.amount if refund else 0)
    
    items = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT * FROM c WHERE c.id = @id AND c.orderId = @order_id",
        [
            {"name": "@id", "value": payment_id},
            {"name": "@order_id", "value": order_id}
        ]
    )
    
    if not items:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    payment = items[0]
    
    if payment["status"] not in [PaymentStatus.CAPTURED.value, PaymentStatus.PARTIALLY_REFUNDED.value]:
        raise HTTPException(
            status_code=400,
            detail="Payment must be captured to refund"
        )
    
    refund_amount = refund.amount if refund else payment["amount"]
    max_refundable = payment["amount"] - payment["refunded_amount"]
    
    if refund_amount > max_refundable:
        raise HTTPException(
            status_code=400,
            detail=f"Refund amount exceeds maximum refundable: {max_refundable}"
        )
    
    new_refunded = payment["refunded_amount"] + refund_amount
    is_full_refund = new_refunded >= payment["amount"]
    
    result = await app.state.cosmos.update_item(
        CONTAINER_NAME,
        payment_id,
        order_id,
        {
            "status": PaymentStatus.REFUNDED.value if is_full_refund else PaymentStatus.PARTIALLY_REFUNDED.value,
            "refunded_amount": new_refunded,
            "updated_at": datetime.utcnow().isoformat()
        }
    )
    
    track_custom_event(
        "payment_refunded",
        properties={
            "payment_id": payment_id,
            "order_id": order_id,
            "reason": refund.reason if refund else "full_refund",
            "is_full": is_full_refund
        },
        measurements={"amount": refund_amount}
    )
    
    logger.info(
        "Payment refunded",
        payment_id=payment_id,
        amount=refund_amount,
        is_full=is_full_refund
    )
    
    return Payment(**result)


@app.get("/api/v1/payments/{payment_id}", response_model=Payment)
@trace_operation("get_payment")
async def get_payment(payment_id: str, order_id: str = Query(...)):
    """Get payment by ID."""
    items = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT * FROM c WHERE c.id = @id AND c.orderId = @order_id",
        [
            {"name": "@id", "value": payment_id},
            {"name": "@order_id", "value": order_id}
        ]
    )
    
    if not items:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    return Payment(**items[0])


@app.get("/api/v1/payments", response_model=List[Payment])
@trace_operation("list_payments")
async def list_payments(
    user_id: str = Query(None),
    order_id: str = Query(None),
    status: PaymentStatus = Query(None)
):
    """List payments with filters."""
    conditions = []
    parameters = []
    
    if user_id:
        conditions.append("c.user_id = @user_id")
        parameters.append({"name": "@user_id", "value": user_id})
    
    if order_id:
        conditions.append("c.orderId = @order_id")
        parameters.append({"name": "@order_id", "value": order_id})
    
    if status:
        conditions.append("c.status = @status")
        parameters.append({"name": "@status", "value": status.value})
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    items = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        f"SELECT * FROM c WHERE {where_clause} ORDER BY c.created_at DESC",
        parameters
    )
    
    return [Payment(**item) for item in items]


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8005")),
        reload=os.getenv("ENV", "development") == "development"
    )
