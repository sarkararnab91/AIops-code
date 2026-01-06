"""
User Service - User Management & Authentication
Handles user registration, profiles, and authentication.
"""

import os
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import (
    configure_telemetry,
    instrument_fastapi,
    TracingMiddleware,
    trace_operation,
    add_span_attribute,
    track_custom_event,
    get_cosmos_client,
    get_redis_client,
    TelemetryLogger,
)


# Configuration
SERVICE_NAME = "user-service"
CONTAINER_NAME = "users"
SESSION_TTL = 86400  # 24 hours

# Initialize telemetry
configure_telemetry(SERVICE_NAME)
logger = TelemetryLogger(SERVICE_NAME)

# Security
security = HTTPBearer(auto_error=False)


# =============================================================================
# MODELS
# =============================================================================

class UserCreate(BaseModel):
    """Request model for user registration."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    phone: Optional[str] = None


class UserLogin(BaseModel):
    """Request model for user login."""
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    """Request model for updating user profile."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    phone: Optional[str] = None
    preferences: Optional[dict] = None


class Address(BaseModel):
    """User address model."""
    id: str
    label: str  # "home", "work", etc.
    full_name: str
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str = "US"
    phone: Optional[str] = None
    is_default: bool = False


class AddressCreate(BaseModel):
    """Request model for adding an address."""
    label: str
    full_name: str
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str = "US"
    phone: Optional[str] = None
    is_default: bool = False


class User(BaseModel):
    """User model (public)."""
    id: str
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    is_active: bool
    preferences: dict = {}
    addresses: List[Address] = []
    created_at: str
    updated_at: str


class AuthToken(BaseModel):
    """Authentication token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: User


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
    logger.info("Starting User Service")
    
    cosmos = await get_cosmos_client()
    redis = await get_redis_client()
    
    app.state.cosmos = cosmos
    app.state.redis = redis
    
    logger.info("User Service started successfully")
    yield
    
    await cosmos.close()
    await redis.close()


app = FastAPI(
    title="User Service",
    description="User management and authentication",
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
# HELPERS
# =============================================================================

def hash_password(password: str) -> str:
    """Hash password using SHA-256 with salt."""
    salt = os.getenv("PASSWORD_SALT", "aiops-training-salt")
    return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash."""
    return hash_password(password) == hashed


def generate_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(32)


async def get_session(token: str) -> Optional[dict]:
    """Get session data from Redis."""
    import json
    session_key = f"session:{token}"
    data = await app.state.redis.get(session_key)
    return json.loads(data) if data else None


async def create_session(user_id: str, email: str) -> str:
    """Create a new session."""
    import json
    token = generate_token()
    session_key = f"session:{token}"
    
    session_data = {
        "user_id": user_id,
        "email": email,
        "created_at": datetime.utcnow().isoformat()
    }
    
    await app.state.redis.set(session_key, json.dumps(session_data), ttl_seconds=SESSION_TTL)
    return token


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """Dependency to get current authenticated user."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    session = await get_session(credentials.credentials)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return session


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


@app.post("/api/v1/users/register", response_model=AuthToken, status_code=201)
@trace_operation("register_user")
async def register_user(user: UserCreate):
    """Register a new user."""
    add_span_attribute("user.email", user.email)
    
    # Check if email exists
    existing = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT c.id FROM c WHERE c.email = @email",
        [{"name": "@email", "value": user.email}]
    )
    
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    user_data = {
        "id": user_id,
        "email": user.email,
        "password_hash": hash_password(user.password),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "is_active": True,
        "preferences": {},
        "addresses": [],
        "created_at": now,
        "updated_at": now,
    }
    
    await app.state.cosmos.create_item(CONTAINER_NAME, user_data)
    
    # Create session
    token = await create_session(user_id, user.email)
    
    track_custom_event(
        "user_registered",
        properties={"user_id": user_id}
    )
    
    logger.info("User registered", user_id=user_id, email=user.email)
    
    # Build response (exclude password)
    user_response = User(
        id=user_id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
        is_active=True,
        preferences={},
        addresses=[],
        created_at=now,
        updated_at=now
    )
    
    return AuthToken(
        access_token=token,
        expires_in=SESSION_TTL,
        user=user_response
    )


@app.post("/api/v1/users/login", response_model=AuthToken)
@trace_operation("login_user")
async def login_user(credentials: UserLogin):
    """Authenticate user and return token."""
    add_span_attribute("user.email", credentials.email)
    
    # Find user
    users = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT * FROM c WHERE c.email = @email",
        [{"name": "@email", "value": credentials.email}]
    )
    
    if not users:
        track_custom_event(
            "login_failed",
            properties={"email": credentials.email, "reason": "user_not_found"}
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user = users[0]
    
    if not verify_password(credentials.password, user["password_hash"]):
        track_custom_event(
            "login_failed",
            properties={"email": credentials.email, "reason": "invalid_password"}
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account is deactivated")
    
    # Create session
    token = await create_session(user["id"], user["email"])
    
    track_custom_event(
        "user_logged_in",
        properties={"user_id": user["id"]}
    )
    
    logger.info("User logged in", user_id=user["id"])
    
    user_response = User(
        id=user["id"],
        email=user["email"],
        first_name=user["first_name"],
        last_name=user["last_name"],
        phone=user.get("phone"),
        is_active=user["is_active"],
        preferences=user.get("preferences", {}),
        addresses=[Address(**addr) for addr in user.get("addresses", [])],
        created_at=user["created_at"],
        updated_at=user["updated_at"]
    )
    
    return AuthToken(
        access_token=token,
        expires_in=SESSION_TTL,
        user=user_response
    )


@app.post("/api/v1/users/logout", status_code=204)
@trace_operation("logout_user")
async def logout_user(session: dict = Depends(get_current_user)):
    """Logout and invalidate session."""
    # Session will expire naturally, but we could explicitly delete if needed
    track_custom_event(
        "user_logged_out",
        properties={"user_id": session["user_id"]}
    )
    logger.info("User logged out", user_id=session["user_id"])


@app.get("/api/v1/users/me", response_model=User)
@trace_operation("get_current_user")
async def get_me(session: dict = Depends(get_current_user)):
    """Get current user profile."""
    users = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT * FROM c WHERE c.id = @id",
        [{"name": "@id", "value": session["user_id"]}]
    )
    
    if not users:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = users[0]
    
    return User(
        id=user["id"],
        email=user["email"],
        first_name=user["first_name"],
        last_name=user["last_name"],
        phone=user.get("phone"),
        is_active=user["is_active"],
        preferences=user.get("preferences", {}),
        addresses=[Address(**addr) for addr in user.get("addresses", [])],
        created_at=user["created_at"],
        updated_at=user["updated_at"]
    )


@app.put("/api/v1/users/me", response_model=User)
@trace_operation("update_profile")
async def update_profile(
    updates: UserUpdate,
    session: dict = Depends(get_current_user)
):
    """Update current user profile."""
    user_id = session["user_id"]
    add_span_attribute("user_id", user_id)
    
    update_data = {k: v for k, v in updates.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.utcnow().isoformat()
    
    result = await app.state.cosmos.update_item(
        CONTAINER_NAME,
        user_id,
        user_id,  # id is the partition key
        update_data
    )
    
    logger.info("Profile updated", user_id=user_id)
    
    return User(
        id=result["id"],
        email=result["email"],
        first_name=result["first_name"],
        last_name=result["last_name"],
        phone=result.get("phone"),
        is_active=result["is_active"],
        preferences=result.get("preferences", {}),
        addresses=[Address(**addr) for addr in result.get("addresses", [])],
        created_at=result["created_at"],
        updated_at=result["updated_at"]
    )


@app.post("/api/v1/users/me/addresses", response_model=Address, status_code=201)
@trace_operation("add_address")
async def add_address(
    address: AddressCreate,
    session: dict = Depends(get_current_user)
):
    """Add a new address."""
    user_id = session["user_id"]
    
    # Get current user
    users = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT * FROM c WHERE c.id = @id",
        [{"name": "@id", "value": user_id}]
    )
    
    if not users:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = users[0]
    addresses = user.get("addresses", [])
    
    # Create new address
    address_id = str(uuid.uuid4())
    new_address = {
        "id": address_id,
        **address.model_dump()
    }
    
    # If this is default, unset other defaults
    if address.is_default:
        for addr in addresses:
            addr["is_default"] = False
    
    addresses.append(new_address)
    
    await app.state.cosmos.update_item(
        CONTAINER_NAME,
        user_id,
        user_id,
        {
            "addresses": addresses,
            "updated_at": datetime.utcnow().isoformat()
        }
    )
    
    track_custom_event(
        "address_added",
        properties={"user_id": user_id, "address_id": address_id}
    )
    
    return Address(**new_address)


@app.get("/api/v1/users/{user_id}", response_model=User)
@trace_operation("get_user")
async def get_user(user_id: str):
    """Get user by ID (for internal service use)."""
    users = await app.state.cosmos.query_items(
        CONTAINER_NAME,
        "SELECT * FROM c WHERE c.id = @id",
        [{"name": "@id", "value": user_id}]
    )
    
    if not users:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = users[0]
    
    return User(
        id=user["id"],
        email=user["email"],
        first_name=user["first_name"],
        last_name=user["last_name"],
        phone=user.get("phone"),
        is_active=user["is_active"],
        preferences=user.get("preferences", {}),
        addresses=[Address(**addr) for addr in user.get("addresses", [])],
        created_at=user["created_at"],
        updated_at=user["updated_at"]
    )


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8006")),
        reload=os.getenv("ENV", "development") == "development"
    )
