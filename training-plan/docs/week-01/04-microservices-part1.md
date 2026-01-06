# Session 4: Microservices Part 1 (Catalog, Inventory, User)

## 📋 Session Details
- **Duration**: 1 hour
- **Week**: 1, Day 4 (Thursday)
- **Prerequisites**: Sessions 1-3 completed, Data services deployed
- **Deliverable**: Catalog, Inventory, and User services running

---

## 🎯 Learning Objectives

By the end of this session, you will:
1. Understand FastAPI microservice structure
2. Build the Catalog Service with Cosmos DB
3. Build the Inventory Service
4. Build the User Service with JWT authentication

---

## 📚 Concepts

### Microservice Architecture Pattern

Each service follows a consistent structure:

```
service-name/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI application entry point
│   ├── config.py         # Configuration and settings
│   ├── models.py         # Pydantic models
│   ├── routes.py         # API endpoints
│   ├── database.py       # Database connection
│   └── services.py       # Business logic
├── tests/
│   └── test_*.py
├── Dockerfile
└── requirements.txt
```

### Service Responsibilities

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SESSION 4 SERVICES                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      CATALOG SERVICE                                 │   │
│  │  • Products CRUD (perfumes, desserts)                               │   │
│  │  • Category management                                               │   │
│  │  • Product search                                                    │   │
│  │  • Database: Cosmos DB (products container)                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      INVENTORY SERVICE                               │   │
│  │  • Stock level tracking                                              │   │
│  │  • Stock reservations                                                │   │
│  │  • Low stock alerts                                                  │   │
│  │  • Database: Cosmos DB (inventory container)                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        USER SERVICE                                  │   │
│  │  • User registration                                                 │   │
│  │  • Authentication (JWT)                                              │   │
│  │  • Profile management                                                │   │
│  │  • Database: Cosmos DB (users container)                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Hands-On Exercise

### Step 1: Create Shared Models Package

First, create shared models used across services:

Create `ecommerce-app/shared/__init__.py`:

```python
"""Shared models and utilities for e-commerce services."""
```

Create `ecommerce-app/shared/models.py`:

```python
"""Shared Pydantic models for e-commerce services."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Category(str, Enum):
    """Product categories."""
    PERFUMES = "perfumes"
    DESSERTS = "desserts"


class ProductBase(BaseModel):
    """Base product model."""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    price: float = Field(..., gt=0)
    category: Category
    image_url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class Product(ProductBase):
    """Full product model with ID and metadata."""
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True


class InventoryItem(BaseModel):
    """Inventory item model."""
    id: str
    product_id: str
    quantity: int = Field(..., ge=0)
    reserved: int = Field(default=0, ge=0)
    low_stock_threshold: int = Field(default=10, ge=0)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    @property
    def available(self) -> int:
        """Available quantity (total - reserved)."""
        return max(0, self.quantity - self.reserved)
    
    @property
    def is_low_stock(self) -> bool:
        """Check if stock is low."""
        return self.available <= self.low_stock_threshold


class UserBase(BaseModel):
    """Base user model."""
    email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    name: str = Field(..., min_length=1, max_length=100)


class User(UserBase):
    """Full user model."""
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    is_verified: bool = False


class UserInDB(User):
    """User model with password hash (for database storage)."""
    password_hash: str
```

### Step 2: Create Catalog Service

Create directory structure:

```bash
mkdir -p ecommerce-app/services/catalog-service/app
mkdir -p ecommerce-app/services/catalog-service/tests
```

Create `ecommerce-app/services/catalog-service/app/__init__.py`:

```python
"""Catalog Service - Product management for e-commerce."""
```

Create `ecommerce-app/services/catalog-service/app/config.py`:

```python
"""Catalog service configuration."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment."""
    
    # Service info
    service_name: str = "catalog-service"
    service_version: str = "1.0.0"
    debug: bool = False
    
    # Cosmos DB
    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database: str = "ecommerce"
    cosmos_container: str = "products"
    
    # Application Insights
    applicationinsights_connection_string: str = ""
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8001
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
```

Create `ecommerce-app/services/catalog-service/app/database.py`:

```python
"""Cosmos DB connection for Catalog Service."""

from azure.cosmos import CosmosClient, ContainerProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from typing import Optional
import structlog

from .config import get_settings

logger = structlog.get_logger()


class CatalogDatabase:
    """Cosmos DB client for catalog operations."""
    
    def __init__(self):
        settings = get_settings()
        self.client = CosmosClient(settings.cosmos_endpoint, settings.cosmos_key)
        self.database = self.client.get_database_client(settings.cosmos_database)
        self.container: ContainerProxy = self.database.get_container_client(
            settings.cosmos_container
        )
        logger.info("catalog_database_initialized", 
                   database=settings.cosmos_database,
                   container=settings.cosmos_container)
    
    async def get_product(self, product_id: str, category: str) -> Optional[dict]:
        """Get a product by ID and category (partition key)."""
        try:
            return self.container.read_item(item=product_id, partition_key=category)
        except CosmosResourceNotFoundError:
            return None
    
    async def list_products(
        self, 
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[dict]:
        """List products, optionally filtered by category."""
        if category:
            query = "SELECT * FROM c WHERE c.category = @category AND c.is_active = true"
            params = [{"name": "@category", "value": category}]
        else:
            query = "SELECT * FROM c WHERE c.is_active = true"
            params = []
        
        query += f" OFFSET {offset} LIMIT {limit}"
        
        items = list(self.container.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True
        ))
        return items
    
    async def create_product(self, product: dict) -> dict:
        """Create a new product."""
        return self.container.create_item(body=product)
    
    async def update_product(self, product: dict) -> dict:
        """Update an existing product."""
        return self.container.upsert_item(body=product)
    
    async def delete_product(self, product_id: str, category: str) -> bool:
        """Soft delete a product."""
        product = await self.get_product(product_id, category)
        if product:
            product["is_active"] = False
            await self.update_product(product)
            return True
        return False
    
    async def search_products(self, search_term: str, limit: int = 20) -> list[dict]:
        """Search products by name or description."""
        query = """
        SELECT * FROM c 
        WHERE c.is_active = true 
        AND (CONTAINS(LOWER(c.name), LOWER(@term)) 
             OR CONTAINS(LOWER(c.description), LOWER(@term)))
        """
        items = list(self.container.query_items(
            query=query,
            parameters=[{"name": "@term", "value": search_term}],
            enable_cross_partition_query=True,
            max_item_count=limit
        ))
        return items


# Global database instance
_db: Optional[CatalogDatabase] = None


def get_database() -> CatalogDatabase:
    """Get or create database instance."""
    global _db
    if _db is None:
        _db = CatalogDatabase()
    return _db
```

Create `ecommerce-app/services/catalog-service/app/routes.py`:

```python
"""Catalog Service API routes."""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
import structlog

from .database import get_database

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.get("/")
async def list_products(
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """List all products with optional filtering."""
    logger.info("list_products", category=category, limit=limit, offset=offset)
    
    db = get_database()
    products = await db.list_products(category=category, limit=limit, offset=offset)
    
    return {
        "items": products,
        "count": len(products),
        "limit": limit,
        "offset": offset
    }


@router.get("/search")
async def search_products(
    q: str = Query(..., min_length=2, description="Search term"),
    limit: int = Query(20, ge=1, le=50)
):
    """Search products by name or description."""
    logger.info("search_products", query=q, limit=limit)
    
    db = get_database()
    products = await db.search_products(search_term=q, limit=limit)
    
    return {
        "items": products,
        "count": len(products),
        "query": q
    }


@router.get("/{product_id}")
async def get_product(product_id: str, category: str = Query(...)):
    """Get a product by ID."""
    logger.info("get_product", product_id=product_id, category=category)
    
    db = get_database()
    product = await db.get_product(product_id, category)
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return product


@router.post("/", status_code=201)
async def create_product(product: dict):
    """Create a new product."""
    logger.info("create_product", name=product.get("name"))
    
    # Add metadata
    product["id"] = str(uuid4())
    product["created_at"] = datetime.utcnow().isoformat()
    product["updated_at"] = datetime.utcnow().isoformat()
    product["is_active"] = True
    
    db = get_database()
    created = await db.create_product(product)
    
    logger.info("product_created", product_id=created["id"])
    return created


@router.put("/{product_id}")
async def update_product(product_id: str, category: str, updates: dict):
    """Update a product."""
    logger.info("update_product", product_id=product_id)
    
    db = get_database()
    existing = await db.get_product(product_id, category)
    
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Merge updates
    existing.update(updates)
    existing["updated_at"] = datetime.utcnow().isoformat()
    
    updated = await db.update_product(existing)
    return updated


@router.delete("/{product_id}")
async def delete_product(product_id: str, category: str):
    """Delete a product (soft delete)."""
    logger.info("delete_product", product_id=product_id)
    
    db = get_database()
    success = await db.delete_product(product_id, category)
    
    if not success:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return {"message": "Product deleted", "product_id": product_id}


@router.get("/categories/list")
async def list_categories():
    """List available product categories."""
    return {
        "categories": [
            {"id": "perfumes", "name": "Perfumes", "description": "Luxury fragrances and colognes"},
            {"id": "desserts", "name": "Desserts", "description": "Gourmet cakes, pastries, and confections"}
        ]
    }
```

Create `ecommerce-app/services/catalog-service/app/main.py`:

```python
"""Catalog Service - FastAPI Application."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from .config import get_settings
from .routes import router as products_router

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("catalog_service_starting", 
               service=settings.service_name,
               version=settings.service_version)
    yield
    logger.info("catalog_service_stopping")


app = FastAPI(
    title="Catalog Service",
    description="Product catalog management for Perfume & Dessert e-commerce",
    version=settings.service_version,
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(products_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.service_version
    }


@app.get("/ready")
async def readiness_check():
    """Readiness check - verifies database connectivity."""
    from .database import get_database
    try:
        db = get_database()
        # Simple query to verify connection
        await db.list_products(limit=1)
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        logger.error("readiness_check_failed", error=str(e))
        return {"status": "not_ready", "database": "disconnected", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
```

### Step 3: Create Inventory Service

Create `ecommerce-app/services/inventory-service/app/main.py`:

```python
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
```

### Step 4: Create User Service

Create `ecommerce-app/services/user-service/app/main.py`:

```python
"""User Service - Authentication and user management."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
import hashlib
import secrets

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr
from pydantic_settings import BaseSettings
from azure.cosmos import CosmosClient, ContainerProxy
import structlog
import jwt

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()


class Settings(BaseSettings):
    service_name: str = "user-service"
    service_version: str = "1.0.0"
    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database: str = "ecommerce"
    cosmos_container: str = "users"
    jwt_secret: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    host: str = "0.0.0.0"
    port: int = 8003
    
    class Config:
        env_file = ".env"


settings = Settings()
security = HTTPBearer()


# Pydantic Models
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str = Field(..., min_length=1, max_length=100)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: str
    is_active: bool

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


# Password hashing
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}:{hashed.hex()}"

def verify_password(password: str, hashed: str) -> bool:
    try:
        salt, hash_value = hashed.split(':')
        new_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return new_hash.hex() == hash_value
    except:
        return False


# JWT functions
def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# Database
class UserDatabase:
    def __init__(self):
        self.client = CosmosClient(settings.cosmos_endpoint, settings.cosmos_key)
        self.database = self.client.get_database_client(settings.cosmos_database)
        self.container: ContainerProxy = self.database.get_container_client(
            settings.cosmos_container
        )
    
    async def get_user_by_id(self, user_id: str) -> Optional[dict]:
        try:
            return self.container.read_item(item=user_id, partition_key=user_id)
        except:
            return None
    
    async def get_user_by_email(self, email: str) -> Optional[dict]:
        query = "SELECT * FROM c WHERE c.email = @email"
        items = list(self.container.query_items(
            query=query,
            parameters=[{"name": "@email", "value": email}],
            enable_cross_partition_query=True
        ))
        return items[0] if items else None
    
    async def create_user(self, user: dict) -> dict:
        return self.container.create_item(body=user)
    
    async def update_user(self, user: dict) -> dict:
        return self.container.upsert_item(body=user)


db: Optional[UserDatabase] = None

def get_db() -> UserDatabase:
    global db
    if db is None:
        db = UserDatabase()
    return db


# Auth dependency
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    payload = decode_token(credentials.credentials)
    user = await get_db().get_user_by_id(payload["sub"])
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("user_service_starting")
    yield
    logger.info("user_service_stopping")


app = FastAPI(
    title="User Service",
    description="Authentication and user management",
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


@app.post("/api/v1/users/register", response_model=TokenResponse)
async def register(user_data: UserCreate):
    """Register a new user."""
    logger.info("user_register", email=user_data.email)
    
    db = get_db()
    
    # Check if email exists
    existing = await db.get_user_by_email(user_data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    user_id = str(uuid4())
    user = {
        "id": user_id,
        "email": user_data.email,
        "name": user_data.name,
        "password_hash": hash_password(user_data.password),
        "created_at": datetime.utcnow().isoformat(),
        "is_active": True,
        "is_verified": False
    }
    
    created = await db.create_user(user)
    
    # Generate token
    token = create_access_token(user_id, user_data.email)
    
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expiration_hours * 3600,
        user=UserResponse(
            id=created["id"],
            email=created["email"],
            name=created["name"],
            created_at=created["created_at"],
            is_active=created["is_active"]
        )
    )


@app.post("/api/v1/users/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    """Login with email and password."""
    logger.info("user_login", email=credentials.email)
    
    db = get_db()
    user = await db.get_user_by_email(credentials.email)
    
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not user.get("is_active"):
        raise HTTPException(status_code=401, detail="Account is disabled")
    
    token = create_access_token(user["id"], user["email"])
    
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expiration_hours * 3600,
        user=UserResponse(
            id=user["id"],
            email=user["email"],
            name=user["name"],
            created_at=user["created_at"],
            is_active=user["is_active"]
        )
    )


@app.get("/api/v1/users/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user profile."""
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        name=current_user["name"],
        created_at=current_user["created_at"],
        is_active=current_user["is_active"]
    )


@app.put("/api/v1/users/me")
async def update_me(
    updates: dict,
    current_user: dict = Depends(get_current_user)
):
    """Update current user profile."""
    logger.info("user_update", user_id=current_user["id"])
    
    # Only allow updating certain fields
    allowed_fields = {"name"}
    filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}
    
    current_user.update(filtered_updates)
    current_user["updated_at"] = datetime.utcnow().isoformat()
    
    db = get_db()
    updated = await db.update_user(current_user)
    
    return UserResponse(
        id=updated["id"],
        email=updated["email"],
        name=updated["name"],
        created_at=updated["created_at"],
        is_active=updated["is_active"]
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
```

### Step 5: Add Requirements and Dockerfiles

Create `ecommerce-app/services/catalog-service/requirements.txt`:

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
python-dotenv>=1.0.0
azure-cosmos>=4.5.0
structlog>=24.1.0
```

Create `ecommerce-app/services/catalog-service/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/

# Expose port
EXPOSE 8001

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### Step 6: Build and Deploy

Build the container images and push to Azure Container Registry:

```bash
# Set your registry name
export REGISTRY_NAME=aiopstrainacr

# Build and push images
az acr build --registry $REGISTRY_NAME --image catalog-service:v1 ./services/catalog-service
az acr build --registry $REGISTRY_NAME --image inventory-service:v1 ./services/inventory-service
az acr build --registry $REGISTRY_NAME --image user-service:v2 ./services/user-service
```

Create Kubernetes manifests in `infrastructure/kubernetes/services/`:

1. `secrets.yaml` (Store Cosmos DB context)
2. `catalog.yaml` (Deployment & Service)
3. `inventory.yaml` (Deployment & Service)
4. `user.yaml` (Deployment & Service)

Deploy to AKS:

```bash
kubectl apply -f infrastructure/kubernetes/services/
```

Verify deployment:

```bash
kubectl get pods
kubectl logs -l app=catalog-service
kubectl logs -l app=inventory-service
kubectl logs -l app=user-service
```

---

##  Verification Checklist

Before moving to the next session, ensure you have:

- [x] Shared models created in `ecommerce-app/shared/`
- [x] Catalog Service with CRUD operations for products
- [x] Inventory Service with stock management
- [x] User Service with JWT authentication
- [x] All services can connect to Cosmos DB
- [x] Health endpoints working (`/health`)

---

## 📖 Key Takeaways

1. **Consistent service structure** makes maintenance easier
2. **Pydantic models** provide validation and documentation
3. **Structured logging** is essential for observability
4. **Health/readiness endpoints** are critical for Kubernetes

---

## 🔜 Next Session Preview

**Session 5: Microservices Part 2**
- Build Cart Service with Redis caching
- Build Payment Service with state machine
- Build Order Service with Service Bus integration
- Build Notification Service

---

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Cosmos DB Python SDK](https://docs.microsoft.com/en-us/azure/cosmos-db/sql/sql-api-sdk-python)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [JWT Authentication](https://jwt.io/introduction)
