"""
Shared Database Module for E-Commerce Microservices
Provides Cosmos DB and Redis clients with telemetry integration.
"""

import os
import time
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from azure.cosmos.aio import CosmosClient
from azure.cosmos import PartitionKey, exceptions as cosmos_exceptions
import redis.asyncio as redis

from .telemetry import (
    get_tracer,
    get_correlation_id,
    add_span_attribute,
    TelemetryLogger
)
from opentelemetry.trace import SpanKind, Status, StatusCode


logger = TelemetryLogger("database")


class CosmosDBClient:
    """
    Cosmos DB client with automatic telemetry.
    Wraps Azure Cosmos DB async client with tracing.
    """
    
    def __init__(self, database_name: str = "ecommerce"):
        self.endpoint = os.getenv("COSMOS_ENDPOINT")
        self.key = os.getenv("COSMOS_KEY")
        self.database_name = database_name
        self.client: Optional[CosmosClient] = None
        self.database = None
        self.tracer = get_tracer("cosmos-db")
    
    async def connect(self) -> None:
        """Initialize Cosmos DB connection."""
        if not self.endpoint or not self.key:
            raise ValueError("COSMOS_ENDPOINT and COSMOS_KEY must be set")
        
        self.client = CosmosClient(self.endpoint, self.key)
        self.database = self.client.get_database_client(self.database_name)
        logger.info("Connected to Cosmos DB", database=self.database_name)
    
    async def close(self) -> None:
        """Close Cosmos DB connection."""
        if self.client:
            await self.client.close()
            logger.info("Closed Cosmos DB connection")
    
    def get_container(self, container_name: str):
        """Get a container client."""
        return self.database.get_container_client(container_name)
    
    async def create_item(
        self,
        container_name: str,
        item: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create an item in a container."""
        with self.tracer.start_as_current_span(
            f"cosmos.create_item.{container_name}",
            kind=SpanKind.CLIENT,
            attributes={
                "db.system": "cosmosdb",
                "db.name": self.database_name,
                "db.cosmosdb.container": container_name,
                "db.operation": "create_item",
                "correlation_id": get_correlation_id()
            }
        ) as span:
            start_time = time.time()
            try:
                container = self.get_container(container_name)
                result = await container.create_item(item)
                
                span.set_attribute("db.cosmosdb.item_id", result.get("id", ""))
                span.set_status(Status(StatusCode.OK))
                
                return result
            except cosmos_exceptions.CosmosHttpResponseError as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error(
                    "Cosmos DB create failed",
                    container=container_name,
                    error=str(e)
                )
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("db.cosmosdb.duration_ms", duration_ms)
    
    async def read_item(
        self,
        container_name: str,
        item_id: str,
        partition_key: str
    ) -> Optional[Dict[str, Any]]:
        """Read an item from a container."""
        with self.tracer.start_as_current_span(
            f"cosmos.read_item.{container_name}",
            kind=SpanKind.CLIENT,
            attributes={
                "db.system": "cosmosdb",
                "db.name": self.database_name,
                "db.cosmosdb.container": container_name,
                "db.operation": "read_item",
                "db.cosmosdb.item_id": item_id,
                "correlation_id": get_correlation_id()
            }
        ) as span:
            start_time = time.time()
            try:
                container = self.get_container(container_name)
                result = await container.read_item(item_id, partition_key=partition_key)
                
                span.set_status(Status(StatusCode.OK))
                return result
            except cosmos_exceptions.CosmosResourceNotFoundError:
                span.set_status(Status(StatusCode.OK))  # Not found is expected
                return None
            except cosmos_exceptions.CosmosHttpResponseError as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("db.cosmosdb.duration_ms", duration_ms)
    
    async def query_items(
        self,
        container_name: str,
        query: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        partition_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Query items from a container."""
        with self.tracer.start_as_current_span(
            f"cosmos.query.{container_name}",
            kind=SpanKind.CLIENT,
            attributes={
                "db.system": "cosmosdb",
                "db.name": self.database_name,
                "db.cosmosdb.container": container_name,
                "db.operation": "query",
                "db.statement": query,
                "correlation_id": get_correlation_id()
            }
        ) as span:
            start_time = time.time()
            try:
                container = self.get_container(container_name)
                
                query_options = {}
                if partition_key:
                    query_options["partition_key"] = partition_key
                
                items = []
                async for item in container.query_items(
                    query=query,
                    parameters=parameters or [],
                    **query_options
                ):
                    items.append(item)
                
                span.set_attribute("db.cosmosdb.item_count", len(items))
                span.set_status(Status(StatusCode.OK))
                
                return items
            except cosmos_exceptions.CosmosHttpResponseError as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("db.cosmosdb.duration_ms", duration_ms)
    
    async def update_item(
        self,
        container_name: str,
        item_id: str,
        partition_key: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an item in a container (replace)."""
        with self.tracer.start_as_current_span(
            f"cosmos.update_item.{container_name}",
            kind=SpanKind.CLIENT,
            attributes={
                "db.system": "cosmosdb",
                "db.name": self.database_name,
                "db.cosmosdb.container": container_name,
                "db.operation": "replace_item",
                "db.cosmosdb.item_id": item_id,
                "correlation_id": get_correlation_id()
            }
        ) as span:
            start_time = time.time()
            try:
                container = self.get_container(container_name)
                
                # Read current item
                current = await container.read_item(item_id, partition_key=partition_key)
                
                # Merge updates
                current.update(updates)
                
                # Replace item
                result = await container.replace_item(item_id, current)
                
                span.set_status(Status(StatusCode.OK))
                return result
            except cosmos_exceptions.CosmosHttpResponseError as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("db.cosmosdb.duration_ms", duration_ms)
    
    async def delete_item(
        self,
        container_name: str,
        item_id: str,
        partition_key: str
    ) -> None:
        """Delete an item from a container."""
        with self.tracer.start_as_current_span(
            f"cosmos.delete_item.{container_name}",
            kind=SpanKind.CLIENT,
            attributes={
                "db.system": "cosmosdb",
                "db.name": self.database_name,
                "db.cosmosdb.container": container_name,
                "db.operation": "delete_item",
                "db.cosmosdb.item_id": item_id,
                "correlation_id": get_correlation_id()
            }
        ) as span:
            start_time = time.time()
            try:
                container = self.get_container(container_name)
                await container.delete_item(item_id, partition_key=partition_key)
                
                span.set_status(Status(StatusCode.OK))
            except cosmos_exceptions.CosmosHttpResponseError as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("db.cosmosdb.duration_ms", duration_ms)


class RedisClient:
    """
    Redis client with automatic telemetry.
    Used for caching and session management.
    """
    
    def __init__(self):
        self.host = os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", "6380"))
        self.password = os.getenv("REDIS_PASSWORD")
        self.ssl = os.getenv("REDIS_SSL", "true").lower() == "true"
        self.client: Optional[redis.Redis] = None
        self.tracer = get_tracer("redis")
    
    async def connect(self) -> None:
        """Initialize Redis connection."""
        self.client = redis.Redis(
            host=self.host,
            port=self.port,
            password=self.password,
            ssl=self.ssl,
            decode_responses=True
        )
        
        # Test connection
        await self.client.ping()
        logger.info("Connected to Redis", host=self.host)
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            await self.client.close()
            logger.info("Closed Redis connection")
    
    async def get(self, key: str) -> Optional[str]:
        """Get a value from Redis."""
        with self.tracer.start_as_current_span(
            "redis.get",
            kind=SpanKind.CLIENT,
            attributes={
                "db.system": "redis",
                "db.operation": "GET",
                "db.redis.key": key,
                "correlation_id": get_correlation_id()
            }
        ) as span:
            start_time = time.time()
            try:
                result = await self.client.get(key)
                span.set_attribute("db.redis.hit", result is not None)
                span.set_status(Status(StatusCode.OK))
                return result
            except redis.RedisError as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("db.redis.duration_ms", duration_ms)
    
    async def set(
        self,
        key: str,
        value: str,
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """Set a value in Redis."""
        with self.tracer.start_as_current_span(
            "redis.set",
            kind=SpanKind.CLIENT,
            attributes={
                "db.system": "redis",
                "db.operation": "SET",
                "db.redis.key": key,
                "db.redis.ttl": ttl_seconds or -1,
                "correlation_id": get_correlation_id()
            }
        ) as span:
            start_time = time.time()
            try:
                if ttl_seconds:
                    result = await self.client.setex(key, ttl_seconds, value)
                else:
                    result = await self.client.set(key, value)
                span.set_status(Status(StatusCode.OK))
                return result
            except redis.RedisError as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("db.redis.duration_ms", duration_ms)
    
    async def delete(self, key: str) -> int:
        """Delete a key from Redis."""
        with self.tracer.start_as_current_span(
            "redis.delete",
            kind=SpanKind.CLIENT,
            attributes={
                "db.system": "redis",
                "db.operation": "DEL",
                "db.redis.key": key,
                "correlation_id": get_correlation_id()
            }
        ) as span:
            try:
                result = await self.client.delete(key)
                span.set_status(Status(StatusCode.OK))
                return result
            except redis.RedisError as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
    
    async def hget(self, name: str, key: str) -> Optional[str]:
        """Get a hash field."""
        with self.tracer.start_as_current_span(
            "redis.hget",
            kind=SpanKind.CLIENT,
            attributes={
                "db.system": "redis",
                "db.operation": "HGET",
                "db.redis.key": f"{name}:{key}",
                "correlation_id": get_correlation_id()
            }
        ) as span:
            try:
                result = await self.client.hget(name, key)
                span.set_status(Status(StatusCode.OK))
                return result
            except redis.RedisError as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
    
    async def hset(self, name: str, mapping: Dict[str, str]) -> int:
        """Set hash fields."""
        with self.tracer.start_as_current_span(
            "redis.hset",
            kind=SpanKind.CLIENT,
            attributes={
                "db.system": "redis",
                "db.operation": "HSET",
                "db.redis.key": name,
                "db.redis.field_count": len(mapping),
                "correlation_id": get_correlation_id()
            }
        ) as span:
            try:
                result = await self.client.hset(name, mapping=mapping)
                span.set_status(Status(StatusCode.OK))
                return result
            except redis.RedisError as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
    
    async def hgetall(self, name: str) -> Dict[str, str]:
        """Get all hash fields."""
        with self.tracer.start_as_current_span(
            "redis.hgetall",
            kind=SpanKind.CLIENT,
            attributes={
                "db.system": "redis",
                "db.operation": "HGETALL",
                "db.redis.key": name,
                "correlation_id": get_correlation_id()
            }
        ) as span:
            try:
                result = await self.client.hgetall(name)
                span.set_attribute("db.redis.field_count", len(result))
                span.set_status(Status(StatusCode.OK))
                return result
            except redis.RedisError as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise


# Singleton instances
_cosmos_client: Optional[CosmosDBClient] = None
_redis_client: Optional[RedisClient] = None


async def get_cosmos_client() -> CosmosDBClient:
    """Get or create Cosmos DB client."""
    global _cosmos_client
    if _cosmos_client is None:
        _cosmos_client = CosmosDBClient()
        await _cosmos_client.connect()
    return _cosmos_client


async def get_redis_client() -> RedisClient:
    """Get or create Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
        await _redis_client.connect()
    return _redis_client


@asynccontextmanager
async def database_lifespan():
    """Context manager for database connections lifecycle."""
    cosmos = await get_cosmos_client()
    redis = await get_redis_client()
    try:
        yield {"cosmos": cosmos, "redis": redis}
    finally:
        await cosmos.close()
        await redis.close()
