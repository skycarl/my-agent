"""
Garden management tools for FastMCP server.
"""

from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from fastmcp import FastMCP

from .models import GardenDB


# Request/Response models for the tools
class AddPlantRequest(BaseModel):
    plant_name: str = Field(..., description="Name of the plant to add")


class GetProduceCountsRequest(BaseModel):
    plant_name: str = Field(..., description="Name of the plant to get produce counts for")


class AddProduceRequest(BaseModel):
    plant_name: str = Field(..., description="Name of the plant to add produce for")
    amount: Decimal = Field(..., gt=0, description="Amount of produce to add (must be positive)")
    notes: Optional[str] = Field(None, description="Optional notes about the harvest")


class PlantResponse(BaseModel):
    name: str
    total_yield: Decimal


class ProduceCountsResponse(BaseModel):
    plant_name: str
    total_yield: Decimal
    harvest_count: int


# Database file path
DB_FILE = Path(__file__).parent.parent.parent / "garden_db.json"

# Global database instance
garden_db = GardenDB.load_from_file(DB_FILE)


def save_db():
    """Save the current database state to file."""
    garden_db.save_to_file(DB_FILE)


def register_garden_tools(server: FastMCP):
    """Register all garden tools with the FastMCP server."""
    
    @server.tool
    def get_plants() -> Dict[str, List[PlantResponse]]:
        """Get all plants in the garden database.
        
        Returns:
            List of all plants with their names and total yields.
        """
        try:
            plants = []
            for plant_name, plant in garden_db.plants.items():
                plants.append(PlantResponse(
                    name=plant.name,
                    total_yield=plant.total_yield
                ))
            
            return {"plants": plants}
        except Exception as e:
            raise RuntimeError(f"Failed to get plants: {str(e)}")

    @server.tool
    def add_plant(plant_name: str) -> Dict[str, str]:
        """Add a new plant to the garden database.
        
        Args:
            plant_name: Name of the plant to add.
            
        Returns:
            Success message confirming the plant was added.
            
        Raises:
            ValueError: If the plant already exists.
        """
        try:
            plant_name = plant_name.strip()
            if not plant_name:
                raise ValueError("Plant name cannot be empty")
            
            garden_db.add_plant(plant_name)
            save_db()
            
            return {"message": f"Plant '{plant_name}' added successfully"}
        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise RuntimeError(f"Failed to add plant: {str(e)}")

    @server.tool
    def get_produce_counts(plant_name: str) -> ProduceCountsResponse:
        """Get the produce counts for a specific plant.
        
        Args:
            plant_name: Name of the plant to get counts for.
            
        Returns:
            Plant information including total yield and harvest count.
            
        Raises:
            ValueError: If the plant is not found.
        """
        try:
            plant_name = plant_name.strip()
            if not plant_name:
                raise ValueError("Plant name cannot be empty")
            
            plant = garden_db.get_plant(plant_name)
            if not plant:
                raise ValueError(f"Plant '{plant_name}' not found in the garden")
            
            return ProduceCountsResponse(
                plant_name=plant.name,
                total_yield=plant.total_yield,
                harvest_count=len(plant.harvests)
            )
        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise RuntimeError(f"Failed to get produce counts: {str(e)}")

    @server.tool
    def add_produce(plant_name: str, amount: Decimal, notes: Optional[str] = None) -> Dict[str, str]:
        """Add produce (harvest) to a specific plant.
        
        Args:
            plant_name: Name of the plant to add produce for.
            amount: Amount of produce to add (must be positive).
            notes: Optional notes about the harvest.
            
        Returns:
            Success message confirming the produce was added.
            
        Raises:
            ValueError: If the plant is not found or amount is invalid.
        """
        try:
            plant_name = plant_name.strip()
            if not plant_name:
                raise ValueError("Plant name cannot be empty")
            
            if amount <= 0:
                raise ValueError("Amount must be positive")
            
            # Add the harvest
            garden_db.add_harvest(plant_name, amount, notes)
            save_db()
            
            # Get updated plant info
            plant = garden_db.get_plant(plant_name)
            if not plant:
                raise RuntimeError(f"Plant '{plant_name}' not found after adding harvest")
            
            return {
                "message": f"Added {amount} to {plant_name}. Total yield is now {plant.total_yield}"
            }
        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise RuntimeError(f"Failed to add produce: {str(e)}")
