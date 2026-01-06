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
