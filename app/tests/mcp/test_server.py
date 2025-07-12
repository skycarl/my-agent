"""
Test script for the garden MCP server.
"""

import pytest
import asyncio
from fastmcp import Client


@pytest.mark.asyncio
async def test_garden_server():
    """Test the garden server functionality."""
    
    # Create client to connect to the MCP server (HTTP transport auto-inferred)
    client = Client("http://localhost:8001")
    
    try:
        async with client:
            print("Connected to Garden MCP Server")
            
            # Test 1: Get plants
            print("\n=== Test 1: Get Plants ===")
            plants = await client.call_tool("get_plants")
            print(f"Plants: {plants}")
            
            # Test 2: Add a new plant
            print("\n=== Test 2: Add New Plant ===")
            result = await client.call_tool("add_plant", {"plant_name": "carrots"})
            print(f"Add plant result: {result}")
            
            # Test 3: Get plants again to verify addition
            print("\n=== Test 3: Get Plants After Addition ===")
            plants = await client.call_tool("get_plants")
            print(f"Plants after adding carrots: {plants}")
            
            # Test 4: Get produce counts for tomatoes
            print("\n=== Test 4: Get Produce Counts ===")
            counts = await client.call_tool("get_produce_counts", {"plant_name": "tomatoes"})
            print(f"Tomatoes produce counts: {counts}")
            
            # Test 5: Add produce to tomatoes
            print("\n=== Test 5: Add Produce ===")
            result = await client.call_tool("add_produce", {
                "plant_name": "tomatoes",
                "amount": "5.5",
                "notes": "First harvest of the season"
            })
            print(f"Add produce result: {result}")
            
            # Test 6: Get produce counts again
            print("\n=== Test 6: Get Produce Counts After Adding ===")
            counts = await client.call_tool("get_produce_counts", {"plant_name": "tomatoes"})
            print(f"Tomatoes produce counts after harvest: {counts}")
            
            # Test 7: Error handling - add negative amount
            print("\n=== Test 7: Error Handling ===")
            try:
                await client.call_tool("add_produce", {
                    "plant_name": "tomatoes",
                    "amount": "-1",
                    "notes": "This should fail"
                })
            except Exception as e:
                print(f"Expected error for negative amount: {e}")
            
            # Test 8: Error handling - nonexistent plant
            try:
                await client.call_tool("get_produce_counts", {"plant_name": "nonexistent"})
            except Exception as e:
                print(f"Expected error for nonexistent plant: {e}")
                
    except Exception as e:
        print(f"Error connecting to server: {e}")
        print("Make sure the MCP server is running on port 8001")


if __name__ == "__main__":
    asyncio.run(test_garden_server()) 