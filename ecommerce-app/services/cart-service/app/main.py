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
