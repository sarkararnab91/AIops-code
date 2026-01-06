#!/usr/bin/env python3
"""Test Cosmos DB connection and basic operations."""

import os
from azure.cosmos import CosmosClient, PartitionKey
from dotenv import load_dotenv

load_dotenv()

def test_cosmos_connection():
    """Test basic Cosmos DB operations."""
    
    # Get connection info from environment or Azure CLI
    endpoint = os.getenv("COSMOS_DB_ENDPOINT")
    key = os.getenv("COSMOS_DB_KEY")
    
    if not endpoint or not key:
        print("❌ Missing COSMOS_DB_ENDPOINT or COSMOS_DB_KEY")
        print("   Set these in your .env file or export them")
        return False
    
    try:
        # Connect to Cosmos DB
        client = CosmosClient(endpoint, key)
        print(f"✅ Connected to Cosmos DB: {endpoint}")
        
        # List databases
        databases = list(client.list_databases())
        print(f"✅ Found {len(databases)} database(s)")
        
        # Check ecommerce database
        database = client.get_database_client("ecommerce")
        containers = list(database.list_containers())
        print(f"✅ Database 'ecommerce' has {len(containers)} container(s):")
        for container in containers:
            print(f"   - {container['id']}")
        
        # Test write to products container
        products = database.get_container_client("products")
        test_product = {
            "id": "test-product-001",
            "name": "Test Perfume",
            "category": "perfumes",
            "price": 49.99,
            "description": "A test product for connectivity verification"
        }
        
        products.upsert_item(test_product)
        print("✅ Successfully wrote test product to 'products' container")
        
        # Read it back
        read_product = products.read_item(item="test-product-001", partition_key="perfumes")
        print(f"✅ Successfully read back: {read_product['name']}")
        
        # Clean up test data
        products.delete_item(item="test-product-001", partition_key="perfumes")
        print("✅ Cleaned up test data")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_cosmos_connection()
    exit(0 if success else 1)
