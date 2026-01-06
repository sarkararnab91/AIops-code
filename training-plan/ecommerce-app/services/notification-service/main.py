"""
Notification Service - Notification Management
Handles sending notifications via email, SMS, and push.
Integrates with Azure Service Bus for async processing.
"""

import os
import uuid
import json
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
    trace_operation,
    add_span_attribute,
    add_span_event,
    track_custom_event,
    get_cosmos_client,
    get_redis_client,
    TelemetryLogger,
)


# Configuration
SERVICE_NAME = "notification-service"
CONTAINER_NAME = "notifications"

# Initialize telemetry
configure_telemetry(SERVICE_NAME)
logger = TelemetryLogger(SERVICE_NAME)


# =============================================================================
# MODELS
# =============================================================================

class NotificationType(str, Enum):
    ORDER_CONFIRMATION = "order_confirmation"
    ORDER_SHIPPED = "order_shipped"
    ORDER_DELIVERED = "order_delivered"
    ORDER_CANCELLED = "order_cancelled"
    PAYMENT_SUCCESS = "payment_success"
    PAYMENT_FAILED = "payment_failed"
    PROMOTION = "promotion"
    ORDER_UPDATE = "order_update"
    SYSTEM = "system"


class NotificationChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    IN_APP = "in_app"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    READ = "read"


class NotificationCreate(BaseModel):
    """Request model for creating a notification."""
    user_id: str
    type: NotificationType
    title: str = Field(..., max_length=200)
    message: str = Field(..., max_length=2000)
    channels: List[NotificationChannel] = Field(default=[NotificationChannel.IN_APP])
    metadata: dict = Field(default_factory=dict)
    scheduled_at: Optional[str] = None  # ISO datetime for scheduled notifications


class Notification(BaseModel):
    """Notification model."""
    id: str
    user_id: str
    type: NotificationType
    title: str
    message: str
    channels: List[NotificationChannel]
    status: NotificationStatus
    metadata: dict = {}
    sent_at: Optional[str] = None
    read_at: Optional[str] = None
    created_at: str
    updated_at: str


class NotificationList(BaseModel):
    """Response model for notification list."""
    items: List[Notification]
    total: int
    unread_count: int


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
    logger.info("Starting Notification Service")
    
    cosmos = await get_cosmos_client()
    redis = await get_redis_client()
    
    app.state.cosmos = cosmos
    app.state.redis = redis
    
    logger.info("Notification Service started successfully")
    yield
    
    await cosmos.close()
    await redis.close()


app = FastAPI(
    title="Notification Service",
    description="Notification management and delivery",
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
# NOTIFICATION SENDERS (Simulated)
# =============================================================================

async def send_email(user_id: str, title: str, message: str, metadata: dict) -> bool:
    """Simulate sending email notification."""
    import asyncio
    import random
    
    # Simulate processing time
    await asyncio.sleep(random.uniform(0.1, 0.3))
    
    # Simulate 95% success rate
    success = random.random() < 0.95
    
    logger.info(
        "Email sent" if success else "Email failed",
        user_id=user_id,
        title=title,
        success=success
    )
    
    return success


async def send_sms(user_id: str, message: str) -> bool:
    """Simulate sending SMS notification."""
    import asyncio
    import random
    
    await asyncio.sleep(random.uniform(0.1, 0.2))
    success = random.random() < 0.90
    
    logger.info(
        "SMS sent" if success else "SMS failed",
        user_id=user_id,
        success=success
    )
    
    return success


async def send_push(user_id: str, title: str, message: str) -> bool:
    """Simulate sending push notification."""
    import asyncio
    import random
    
    await asyncio.sleep(random.uniform(0.05, 0.15))
    success = random.random() < 0.98
    
    logger.info(
        "Push sent" if success else "Push failed",
        user_id=user_id,
        title=title,
        success=success
    )
    
    return success


async def process_notification(notification_id: str, notification_data: dict):
    """Process and send notification through all channels."""
    channels = notification_data["channels"]
    user_id = notification_data["user_id"]
    title = notification_data["title"]
    message = notification_data["message"]
    metadata = notification_data.get("metadata", {})
    
    results = {}
    
    for channel in channels:
        if channel == NotificationChannel.EMAIL.value:
            results[channel] = await send_email(user_id, title, message, metadata)
        elif channel == NotificationChannel.SMS.value:
            results[channel] = await send_sms(user_id, message)
        elif channel == NotificationChannel.PUSH.value:
            results[channel] = await send_push(user_id, title, message)
        elif channel == NotificationChannel.IN_APP.value:
            results[channel] = True  # In-app is always stored
    
    # Update notification status
    all_success = all(results.values())
    now = datetime.utcnow().isoformat()
    
    try:
        await app.state.cosmos.update_item(
            CONTAINER_NAME,
            notification_id,
            user_id,
            {
                "status": NotificationStatus.SENT.value if all_success else NotificationStatus.FAILED.value,
                "sent_at": now,
                "updated_at": now,
                "delivery_results": results
            }
        )
    except Exception as e:
        logger.error("Failed to update notification status", error=str(e))


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


@app.post("/api/v1/notifications", response_model=Notification, status_code=201)
@trace_operation("create_notification")
async def create_notification(
    notification: NotificationCreate,
    background_tasks: BackgroundTasks
):
    """Create and send a notification."""
    notification_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    add_span_attribute("notification.id", notification_id)
    add_span_attribute("notification.type", notification.type.value)
    add_span_attribute("notification.user_id", notification.user_id)
    add_span_attribute("notification.channels", len(notification.channels))
    
    notification_data = {
        "id": notification_id,
        "userId": notification.user_id,  # Partition key
        "user_id": notification.user_id,
        "type": notification.type.value,
        "title": notification.title,
        "message": notification.message,
        "channels": [c.value for c in notification.channels],
        "status": NotificationStatus.PENDING.value,
        "metadata": notification.metadata,
        "sent_at": None,
        "read_at": None,
        "created_at": now,
        "updated_at": now,
    }
    
    await app.state.cosmos.create_item(CONTAINER_NAME, notification_data)
    
    # Update unread count in cache
    unread_key = f"unread:{notification.user_id}"
    try:
        current = await app.state.redis.get(unread_key)
        count = int(current) + 1 if current else 1
        await app.state.redis.set(unread_key, str(count), ttl_seconds=3600)
    except Exception as e:
        logger.warning("Failed to update unread count", error=str(e))
    
    # Process notification in background
    if not notification.scheduled_at:
        background_tasks.add_task(
            process_notification,
            notification_id,
            notification_data
        )
    
    track_custom_event(
        "notification_created",
        properties={
            "notification_id": notification_id,
            "type": notification.type.value,
            "user_id": notification.user_id
        },
        measurements={"channel_count": len(notification.channels)}
    )
    
    logger.info(
        "Notification created",
        notification_id=notification_id,
        type=notification.type.value
    )
    
    return Notification(**notification_data)


@app.get("/api/v1/notifications", response_model=NotificationList)
@trace_operation("list_notifications")
async def list_notifications(
    user_id: str = Query(...),
    type: Optional[NotificationType] = None,
    unread_only: bool = False,
    limit: int = Query(20, ge=1, le=100)
):
    """List notifications for a user."""
    add_span_attribute("user_id", user_id)
    
    conditions = ["c.userId = @user_id"]
    parameters = [{"name": "@user_id", "value": user_id}]
    
    if type:
        conditions.append("c.type = @type")
        parameters.append({"name": "@type", "value": type.value})
    
    if unread_only:
        conditions.append("c.read_at = null")
    
    where_clause = " AND ".join(conditions)
    
    # Get notifications
    query = f"""
        SELECT * FROM c 
        WHERE {where_clause}
        ORDER BY c.created_at DESC
        OFFSET 0 LIMIT @limit
    """
    parameters.append({"name": "@limit", "value": limit})
    
    items = await app.state.cosmos.query_items(CONTAINER_NAME, query, parameters)
    
    # Count total and unread
    count_query = f"SELECT VALUE COUNT(1) FROM c WHERE {where_clause}"
    count_params = [p for p in parameters if p["name"] != "@limit"]
    total_result = await app.state.cosmos.query_items(CONTAINER_NAME, count_query, count_params)
    total = total_result[0] if total_result else 0
    
    unread_query = f"SELECT VALUE COUNT(1) FROM c WHERE c.userId = @user_id AND c.read_at = null"
    unread_result = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        unread_query,
        [{"name": "@user_id", "value": user_id}]
    )
    unread_count = unread_result[0] if unread_result else 0
    
    return NotificationList(
        items=[Notification(**item) for item in items],
        total=total,
        unread_count=unread_count
    )


@app.put("/api/v1/notifications/{notification_id}/read", response_model=Notification)
@trace_operation("mark_as_read")
async def mark_as_read(notification_id: str, user_id: str = Query(...)):
    """Mark a notification as read."""
    add_span_attribute("notification.id", notification_id)
    
    # Get notification
    items = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT * FROM c WHERE c.id = @id AND c.userId = @user_id",
        [
            {"name": "@id", "value": notification_id},
            {"name": "@user_id", "value": user_id}
        ]
    )
    
    if not items:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    now = datetime.utcnow().isoformat()
    
    result = await app.state.cosmos.update_item(
        CONTAINER_NAME,
        notification_id,
        user_id,
        {
            "status": NotificationStatus.READ.value,
            "read_at": now,
            "updated_at": now
        }
    )
    
    # Update unread count
    unread_key = f"unread:{user_id}"
    try:
        current = await app.state.redis.get(unread_key)
        if current and int(current) > 0:
            await app.state.redis.set(unread_key, str(int(current) - 1), ttl_seconds=3600)
    except Exception:
        pass
    
    track_custom_event(
        "notification_read",
        properties={"notification_id": notification_id, "user_id": user_id}
    )
    
    return Notification(**result)


@app.put("/api/v1/notifications/read-all", status_code=204)
@trace_operation("mark_all_read")
async def mark_all_read(user_id: str = Query(...)):
    """Mark all notifications as read for a user."""
    add_span_attribute("user_id", user_id)
    
    # Get all unread notifications
    items = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT c.id FROM c WHERE c.userId = @user_id AND c.read_at = null",
        [{"name": "@user_id", "value": user_id}]
    )
    
    now = datetime.utcnow().isoformat()
    
    for item in items:
        try:
            await app.state.cosmos.update_item(
                CONTAINER_NAME,
                item["id"],
                user_id,
                {
                    "status": NotificationStatus.READ.value,
                    "read_at": now,
                    "updated_at": now
                }
            )
        except Exception as e:
            logger.warning("Failed to mark notification as read", notification_id=item["id"], error=str(e))
    
    # Reset unread count
    unread_key = f"unread:{user_id}"
    await app.state.redis.set(unread_key, "0", ttl_seconds=3600)
    
    track_custom_event(
        "all_notifications_read",
        properties={"user_id": user_id},
        measurements={"count": len(items)}
    )
    
    logger.info("All notifications marked as read", user_id=user_id, count=len(items))


@app.get("/api/v1/notifications/unread-count")
@trace_operation("get_unread_count")
async def get_unread_count(user_id: str = Query(...)):
    """Get unread notification count for a user."""
    # Try cache first
    unread_key = f"unread:{user_id}"
    cached = await app.state.redis.get(unread_key)
    
    if cached:
        return {"user_id": user_id, "unread_count": int(cached)}
    
    # Query database
    result = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT VALUE COUNT(1) FROM c WHERE c.userId = @user_id AND c.read_at = null",
        [{"name": "@user_id", "value": user_id}]
    )
    
    count = result[0] if result else 0
    
    # Cache result
    await app.state.redis.set(unread_key, str(count), ttl_seconds=3600)
    
    return {"user_id": user_id, "unread_count": count}


@app.delete("/api/v1/notifications/{notification_id}", status_code=204)
@trace_operation("delete_notification")
async def delete_notification(notification_id: str, user_id: str = Query(...)):
    """Delete a notification."""
    try:
        await app.state.cosmos.delete_item(
            CONTAINER_NAME,
            notification_id,
            user_id
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    logger.info("Notification deleted", notification_id=notification_id)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8007")),
        reload=os.getenv("ENV", "development") == "development"
    )
