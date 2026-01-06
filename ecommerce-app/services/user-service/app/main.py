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
