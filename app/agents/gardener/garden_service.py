"""
Garden service — pure business logic for garden management.

Exposes plain functions that agents call directly via @function_tool.
"""

from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel

from .models import GardenDB, Plant
from app.core.settings import config


def normalize_plant_name(plant_name: str, available_plants: List[str]) -> str:
    """
    Normalize plant name to match available plants.

    Tries exact match first, then plural/singular variations.

    Raises:
        ValueError: If no match is found, with suggestions for available plants.
    """
    plant_lower = plant_name.lower().strip()

    if not plant_lower:
        raise ValueError("Plant name cannot be empty")

    # Try exact match first
    if plant_lower in available_plants:
        return plant_lower

    # Try plural/singular variations
    if plant_lower.endswith("s") and len(plant_lower) > 1:
        singular = plant_lower[:-1]
        if singular in available_plants:
            return singular
    else:
        plural = plant_lower + "s"
        if plural in available_plants:
            return plural

    # Try common plural forms
    if plant_lower.endswith("y") and len(plant_lower) > 1:
        ies_form = plant_lower[:-1] + "ies"
        if ies_form in available_plants:
            return ies_form

    if plant_lower.endswith("ies") and len(plant_lower) > 3:
        y_form = plant_lower[:-3] + "y"
        if y_form in available_plants:
            return y_form

    available_list = ", ".join(sorted(available_plants))
    raise ValueError(
        f"Plant '{plant_name}' not found in the garden. Available plants: {available_list}"
    )


class ProduceCountsResponse(BaseModel):
    plant_name: str
    total_yield: Decimal
    harvest_count: int


# Database file path
if not config.garden_db_path:
    raise ValueError("GARDEN_DB_PATH is not configured in settings")

DB_FILE = Path(config.garden_db_path)

# Global database instance
garden_db = GardenDB.load_from_file(DB_FILE)


def save_db():
    """Save the current database state to file."""
    garden_db.save_to_file(DB_FILE)


def get_plants() -> Dict[str, Dict[str, Plant]]:
    """Get all plants in the garden database."""
    return {"plants": garden_db.plants}


def add_plant(plant_name: str) -> Dict[str, str]:
    """Add a new plant to the garden database."""
    plant_name = plant_name.strip()
    if not plant_name:
        raise ValueError("Plant name cannot be empty")

    garden_db.add_plant(plant_name)
    save_db()
    return {"message": f"Plant '{plant_name}' added successfully"}


def get_produce_counts(plant_name: str) -> ProduceCountsResponse:
    """Get the produce counts for a specific plant."""
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


def add_produce(
    plant_name: str, amount: Decimal, notes: Optional[str] = None
) -> Dict[str, str]:
    """Add produce (harvest) to a specific plant."""
    if amount <= 0:
        raise ValueError("Amount must be positive")

    available_plants = garden_db.get_plant_names()
    normalized_name = normalize_plant_name(plant_name, available_plants)

    garden_db.add_harvest(normalized_name, amount, notes)
    save_db()

    plant = garden_db.get_plant(normalized_name)
    return {
        "message": f"Added {amount} to {plant.name}. Total yield is now {plant.total_yield}"
    }
