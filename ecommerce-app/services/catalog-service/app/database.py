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
