"""
Garden database models using Pydantic for data validation and serialization.
"""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


class Harvest(BaseModel):
    """Represents a single harvest from a plant."""

    date: datetime = Field(..., description="Date of the harvest")
    yield_amount: Decimal = Field(
        ..., gt=0, description="Amount harvested (must be positive)"
    )
    notes: Optional[str] = Field(None, description="Optional notes about the harvest")

    @field_validator("yield_amount")
    @classmethod
    def validate_yield_amount(cls, v):
        """Ensure yield amount is positive."""
        if v <= 0:
            raise ValueError("Yield amount must be positive")
        return v

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat(), Decimal: str}
    )


class Plant(BaseModel):
    """Represents a plant in the garden with its harvests."""

    name: str = Field(..., description="Name of the plant")
    harvests: List[Harvest] = Field(
        default_factory=list, description="List of harvests"
    )
    total_yield: Decimal = Field(
        default=Decimal("0"), description="Total yield across all harvests"
    )

    def add_harvest(self, harvest: Harvest) -> None:
        """Add a new harvest and update total yield."""
        self.harvests.append(harvest)
        self.total_yield += harvest.yield_amount

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat(), Decimal: str}
    )


class GardenDB(BaseModel):
    """Garden database containing all plants."""

    plants: Dict[str, Plant] = Field(
        default_factory=dict, description="Plants in the garden"
    )

    @classmethod
    def load_from_file(cls, file_path: Path) -> "GardenDB":
        """Load garden database from JSON file."""
        if not file_path.exists():
            # Create default database with initial plants
            garden_db = cls()
            garden_db.initialize_default_plants()
            return garden_db

        with open(file_path, "r") as f:
            data = json.load(f)
            return cls(**data)

    def save_to_file(self, file_path: Path) -> None:
        """Save garden database to JSON file."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            json.dump(self.dict(), f, indent=2, default=self._json_encoder)

    def initialize_default_plants(self) -> None:
        """Initialize the database with default plants."""
        default_plants = ["peas", "tomatoes", "squash", "cucumbers"]
        for plant_name in default_plants:
            self.plants[plant_name] = Plant(name=plant_name)

    def add_plant(self, plant_name: str) -> None:
        """Add a new plant to the garden."""
        if plant_name.lower() in self.plants:
            raise ValueError(f"Plant '{plant_name}' already exists in the garden")

        self.plants[plant_name.lower()] = Plant(name=plant_name.lower())

    def get_plant(self, plant_name: str) -> Optional[Plant]:
        """Get a plant by name."""
        return self.plants.get(plant_name.lower())

    def get_plant_names(self) -> List[str]:
        """Get list of all plant names."""
        return list(self.plants.keys())

    def add_harvest(
        self, plant_name: str, yield_amount: Decimal, notes: Optional[str] = None
    ) -> None:
        """Add a harvest to a specific plant."""
        plant = self.get_plant(plant_name)
        if not plant:
            raise ValueError(f"Plant '{plant_name}' not found in the garden")

        harvest = Harvest(date=datetime.now(), yield_amount=yield_amount, notes=notes)
        plant.add_harvest(harvest)

    @staticmethod
    def _json_encoder(obj):
        """Custom JSON encoder for special types."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return str(obj)
        return obj

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat(), Decimal: str}
    )
