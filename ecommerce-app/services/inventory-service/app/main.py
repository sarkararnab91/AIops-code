"""Inventory Service - Stock management for e-commerce."""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from azure.cosmos import CosmosClient, ContainerProxy
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()


class Settings(BaseSettings):
    service_name: str = "inventory-service"
    service_version: str = "1.0.0"
    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database: str = "ecommerce"
    cosmos_container: str = "inventory"
    host: str = "0.0.0.0"
    port: int = 8002
    
    class Config:
        env_file = ".env"


settings = Settings()


# Pydantic Models
class StockUpdate(BaseModel):
    quantity: int = Field(..., ge=0)
    
class ReservationRequest(BaseModel):
    product_id: str
    quantity: int = Field(..., gt=0)
    order_id: str

class InventoryItem(BaseModel):
    id: str
    product_id: str
    quantity: int = 0
    reserved: int = 0
    low_stock_threshold: int = 10
    last_updated: str


# Database
class InventoryDatabase:
    def __init__(self):
        self.client = CosmosClient(settings.cosmos_endpoint, settings.cosmos_key)
        self.database = self.client.get_database_client(settings.cosmos_database)
        self.container: ContainerProxy = self.database.get_container_client(
            settings.cosmos_container
        )
    
    async def get_inventory(self, product_id: str) -> Optional[dict]:
        try:
            return self.container.read_item(item=product_id, partition_key=product_id)
        except:
            return None
    
    async def upsert_inventory(self, item: dict) -> dict:
        return self.container.upsert_item(body=item)
    
    async def list_low_stock(self, threshold: int = 10) -> list[dict]:
        query = """
        SELECT * FROM c 
        WHERE (c.quantity - c.reserved) <= @threshold
        """
        return list(self.container.query_items(
            query=query,
            parameters=[{"name": "@threshold", "value": threshold}],
            enable_cross_partition_query=True
        ))


db: Optional[InventoryDatabase] = None


def get_db() -> InventoryDatabase:
    global db
    if db is None:
        db = InventoryDatabase()
    return db


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("inventory_service_starting")
    yield
    logger.info("inventory_service_stopping")


app = FastAPI(
    title="Inventory Service",
    description="Stock management for e-commerce",
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


@app.get("/api/v1/inventory/{product_id}")
async def get_inventory(product_id: str):
    """Get inventory for a product."""
    item = await get_db().get_inventory(product_id)
    if not item:
        raise HTTPException(status_code=404, detail="Inventory not found")
    
    item["available"] = item["quantity"] - item["reserved"]
    item["is_low_stock"] = item["available"] <= item.get("low_stock_threshold", 10)
    return item


@app.put("/api/v1/inventory/{product_id}")
async def update_stock(product_id: str, update: StockUpdate):
    """Update stock quantity for a product."""
    logger.info("update_stock", product_id=product_id, quantity=update.quantity)
    
    db = get_db()
    existing = await db.get_inventory(product_id)
    
    if existing:
        existing["quantity"] = update.quantity
        existing["last_updated"] = datetime.utcnow().isoformat()
    else:
        existing = {
            "id": product_id,
            "product_id": product_id,
            "quantity": update.quantity,
            "reserved": 0,
            "low_stock_threshold": 10,
            "last_updated": datetime.utcnow().isoformat()
        }
    
    return await db.upsert_inventory(existing)


@app.post("/api/v1/inventory/reserve")
async def reserve_stock(request: ReservationRequest):
    """Reserve stock for an order."""
    logger.info("reserve_stock", 
               product_id=request.product_id, 
               quantity=request.quantity,
               order_id=request.order_id)
    
    db = get_db()
    item = await db.get_inventory(request.product_id)
    
    if not item:
        raise HTTPException(status_code=404, detail="Product not in inventory")
    
    available = item["quantity"] - item["reserved"]
    if available < request.quantity:
        raise HTTPException(
            status_code=400, 
            detail=f"Insufficient stock. Available: {available}, Requested: {request.quantity}"
        )
    
    item["reserved"] += request.quantity
    item["last_updated"] = datetime.utcnow().isoformat()
    
    updated = await db.upsert_inventory(item)
    
    return {
        "reservation_id": str(uuid4()),
        "product_id": request.product_id,
        "quantity_reserved": request.quantity,
        "order_id": request.order_id,
        "available_after": updated["quantity"] - updated["reserved"]
    }


@app.post("/api/v1/inventory/release")
async def release_reservation(request: ReservationRequest):
    """Release a stock reservation."""
    logger.info("release_stock", product_id=request.product_id, quantity=request.quantity)
    
    db = get_db()
    item = await db.get_inventory(request.product_id)
    
    if not item:
        raise HTTPException(status_code=404, detail="Product not in inventory")
    
    item["reserved"] = max(0, item["reserved"] - request.quantity)
    item["last_updated"] = datetime.utcnow().isoformat()
    
    return await db.upsert_inventory(item)


@app.get("/api/v1/inventory/low-stock")
async def get_low_stock(threshold: int = Query(10, ge=0)):
    """Get all products with low stock."""
    items = await get_db().list_low_stock(threshold)
    return {
        "items": items,
        "count": len(items),
        "threshold": threshold
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
