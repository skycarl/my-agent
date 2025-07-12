# Garden MCP Server

A FastMCP server for managing garden statistics and harvest tracking.

## Overview

This MCP server provides tools for tracking garden plants and their harvests. It uses Pydantic models for data validation and serializes data to JSON for persistence.

## Features

- **Plant Management**: Add and track different plants in your garden
- **Harvest Tracking**: Record harvests with dates, amounts, and notes
- **Data Persistence**: Automatically saves data to JSON file
- **Error Handling**: Validates input and provides meaningful error messages
- **HTTP Transport**: Runs as a web service using FastMCP's HTTP transport

## Default Plants

The server starts with these default plants:
- Peas
- Tomatoes
- Squash
- Cucumbers

## Tools

### 1. `get_plants`
Returns a list of all plants in the garden with their total yields.

**Parameters**: None

**Returns**: List of plants with names and total yields

### 2. `add_plant`
Adds a new plant to the garden database.

**Parameters**:
- `plant_name` (string, required): Name of the plant to add

**Returns**: Success message

**Errors**: ValueError if plant already exists

### 3. `get_produce_counts`
Gets the produce counts for a specific plant.

**Parameters**:
- `plant_name` (string, required): Name of the plant to get counts for

**Returns**: Plant information including total yield and harvest count

**Errors**: ValueError if plant not found

### 4. `add_produce`
Adds a harvest to a specific plant.

**Parameters**:
- `plant_name` (string, required): Name of the plant
- `amount` (decimal, required): Amount harvested (must be positive)
- `notes` (string, optional): Optional notes about the harvest

**Returns**: Success message with updated total yield

**Errors**: ValueError if plant not found or amount is negative

## Running the Server

### Standalone
```bash
python -m my_mcp.garden.server
```

### Using main entry point
```bash
python -m my_mcp.main
```

### With Docker Compose
```bash
docker-compose up mcp-server
```

The server runs on port 8001 by default.

## Testing

Run the test script to verify functionality:
```bash
python -m my_mcp.garden.test_server
```

Make sure the server is running before executing tests.

## Data Storage

The server stores data in `my_mcp/garden/garden_db.json`. This file is automatically created and updated when plants or harvests are added.

## Example Usage

### Getting Plants
```python
from fastmcp import Client

async def example():
    client = Client("http://localhost:8001")
    async with client:
        plants = await client.call_tool("get_plants")
        print(plants)
```

### Adding a Harvest
```python
from fastmcp import Client

async def example():
    client = Client("http://localhost:8001")
    async with client:
        result = await client.call_tool("add_produce", {
            "plant_name": "tomatoes",
            "amount": "5.5",
            "notes": "First harvest of the season"
        })
        print(result)
```

## Architecture

The server uses:
- **FastMCP**: For the MCP server framework
- **Pydantic**: For data validation and serialization
- **HTTP Transport**: For web-based deployment
- **JSON**: For data persistence

## Integration

This MCP server is designed to run as a Docker container alongside your main application. The docker-compose.yml includes the MCP server configuration to run on port 8001.

The server can be integrated with LLM applications to provide garden management capabilities through the MCP protocol. 