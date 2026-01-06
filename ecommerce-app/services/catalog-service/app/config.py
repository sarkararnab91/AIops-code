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
