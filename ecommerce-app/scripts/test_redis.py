#!/usr/bin/env python3
"""Test Redis connection and basic operations."""

import os
import redis
from dotenv import load_dotenv

load_dotenv()

def test_redis_connection():
    """Test basic Redis operations."""
    
    host = os.getenv("REDIS_HOST")
    password = os.getenv("REDIS_PASSWORD")
    port = int(os.getenv("REDIS_PORT", 6380))
    
    if not host or not password:
        print("❌ Missing REDIS_HOST or REDIS_PASSWORD")
        print("   Set these in your .env file or export them")
        return False
    
    try:
        # Connect to Redis (Azure Redis requires SSL)
        client = redis.Redis(
            host=host,
            port=port,
            password=password,
            ssl=True,
            ssl_cert_reqs=None
        )
        
        # Test connection
        pong = client.ping()
        print(f"✅ Connected to Redis: {host}")
        print(f"✅ PING response: {pong}")
        
        # Test write
        client.set("test:key", "Hello from AIOps Training!")
        print("✅ Successfully wrote test key")
        
        # Test read
        value = client.get("test:key")
        print(f"✅ Read value: {value.decode()}")
        
        # Test delete
        client.delete("test:key")
        print("✅ Cleaned up test key")
        
        # Get info
        info = client.info("memory")
        print(f"✅ Redis memory used: {info['used_memory_human']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_redis_connection()
    exit(0 if success else 1)
