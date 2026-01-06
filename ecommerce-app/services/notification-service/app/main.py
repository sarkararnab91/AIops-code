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
