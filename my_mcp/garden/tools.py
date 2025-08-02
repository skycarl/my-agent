"""
Garden management tools for FastMCP server.
"""

from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from fastmcp import FastMCP


from .models import GardenDB
from app.core.settings import config


def normalize_plant_name(plant_name: str, available_plants: List[str]) -> str:
    """
    Normalize plant name to match available plants.

    Tries exact match first, then plural/singular variations.

    Args:
        plant_name: The plant name to normalize
        available_plants: List of available plant names

    Returns:
        The normalized plant name that matches an available plant

    Raises:
        ValueError: If no match is found, with suggestions for available plants
    """
    plant_lower = plant_name.lower().strip()

    if not plant_lower:
        raise ValueError("Plant name cannot be empty")

    # Try exact match first
    if plant_lower in available_plants:
        return plant_lower

    # Try plural/singular variations
    # If input ends with 's', try removing it (peas -> pea)
    if plant_lower.endswith("s") and len(plant_lower) > 1:
        singular = plant_lower[:-1]
        if singular in available_plants:
            return singular

    # If input doesn't end with 's', try adding it (pea -> peas)
    else:
        plural = plant_lower + "s"
        if plural in available_plants:
            return plural

    # Try some common plural forms
    if plant_lower.endswith("y") and len(plant_lower) > 1:
        # Try y -> ies (berry -> berries)
        ies_form = plant_lower[:-1] + "ies"
        if ies_form in available_plants:
            return ies_form

    if plant_lower.endswith("ies") and len(plant_lower) > 3:
        # Try ies -> y (berries -> berry)
        y_form = plant_lower[:-3] + "y"
        if y_form in available_plants:
            return y_form

    # No match found - raise error with available plants
    available_list = ", ".join(sorted(available_plants))
    raise ValueError(
        f"Plant '{plant_name}' not found in the garden. Available plants: {available_list}"
    )


# Request/Response models for the tools
class AddPlantRequest(BaseModel):
    plant_name: str = Field(..., description="Name of the plant to add")


class GetProduceCountsRequest(BaseModel):
    plant_name: str = Field(
        ..., description="Name of the plant to get produce counts for"
    )


class AddProduceRequest(BaseModel):
    plant_name: str = Field(..., description="Name of the plant to add produce for")
    amount: Decimal = Field(
        ..., gt=0, description="Amount of produce to add (must be positive)"
    )
    notes: Optional[str] = Field(None, description="Optional notes about the harvest")


class PlantResponse(BaseModel):
    name: str
    total_yield: Decimal


class ProduceCountsResponse(BaseModel):
    plant_name: str
    total_yield: Decimal
    harvest_count: int


# Database file path - configurable via settings
if not config.garden_db_path:
    raise ValueError("GARDEN_DB_PATH is not configured in settings")

DB_FILE = Path(config.garden_db_path)


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
                plants.append(
                    PlantResponse(name=plant.name, total_yield=plant.total_yield)
                )

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
            # Normalize plant name to handle plural/singular variations
            available_plants = garden_db.get_plant_names()
            normalized_name = normalize_plant_name(plant_name, available_plants)

            plant = garden_db.get_plant(normalized_name)
            if not plant:
                raise ValueError(f"Plant '{plant_name}' not found in the garden")

            return ProduceCountsResponse(
                plant_name=plant.name,
                total_yield=plant.total_yield,
                harvest_count=len(plant.harvests),
            )
        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise RuntimeError(f"Failed to get produce counts: {str(e)}")

    @server.tool
    def add_produce(
        plant_name: str, amount: Decimal, notes: Optional[str] = None
    ) -> Dict[str, str]:
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
            if amount <= 0:
                raise ValueError("Amount must be positive")

            # Normalize plant name to handle plural/singular variations
            available_plants = garden_db.get_plant_names()
            normalized_name = normalize_plant_name(plant_name, available_plants)

            # Add the harvest
            garden_db.add_harvest(normalized_name, amount, notes)
            save_db()

            # Get updated plant info
            plant = garden_db.get_plant(normalized_name)
            if not plant:
                raise RuntimeError(
                    f"Plant '{normalized_name}' not found after adding harvest"
                )

            return {
                "message": f"Added {amount} to {plant.name}. Total yield is now {plant.total_yield}"
            }
        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise RuntimeError(f"Failed to add produce: {str(e)}")
