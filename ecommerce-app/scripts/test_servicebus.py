#!/usr/bin/env python3
"""Test Service Bus connection and basic operations."""

import os
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from dotenv import load_dotenv

load_dotenv()

def test_servicebus_connection():
    """Test basic Service Bus operations."""
    
    connection_string = os.getenv("SERVICE_BUS_CONNECTION_STRING")
    
    if not connection_string:
        print("❌ Missing SERVICE_BUS_CONNECTION_STRING")
        print("   Set this in your .env file or export it")
        return False
    
    try:
        # Connect to Service Bus
        client = ServiceBusClient.from_connection_string(connection_string)
        print("✅ Connected to Service Bus")
        
        # Test sending to orders-queue
        with client.get_queue_sender("orders-queue") as sender:
            message = ServiceBusMessage(
                body="Test order message",
                application_properties={"test": True}
            )
            sender.send_messages(message)
            print("✅ Sent test message to 'orders-queue'")
        
        # Test receiving from orders-queue
        with client.get_queue_receiver("orders-queue", max_wait_time=5) as receiver:
            messages = receiver.receive_messages(max_message_count=1)
            for msg in messages:
                print(f"✅ Received message: {str(msg)}")
                receiver.complete_message(msg)
                print("✅ Completed (acknowledged) message")
        
        return True
        
    except Exception as e:
        print(f" Error: {e}")
        return False

if __name__ == "__main__":
    success = test_servicebus_connection()
    exit(0 if success else 1)
