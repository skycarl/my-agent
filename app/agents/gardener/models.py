"""
Garden database models using Pydantic for data validation and serialization.
"""

import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger
from pydantic import BaseModel, Field, computed_field, field_validator
from app.core.timezone_utils import now_local


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


class Plant(BaseModel):
    """Represents a plant in the garden with its harvests."""

    name: str = Field(..., description="Name of the plant")
    harvests: List[Harvest] = Field(
        default_factory=list, description="List of harvests"
    )

    @computed_field
    @property
    def total_yield(self) -> Decimal:
        """Total yield computed from all harvests."""
        return sum((h.yield_amount for h in self.harvests), Decimal("0"))

    def add_harvest(self, harvest: Harvest) -> None:
        """Add a new harvest."""
        self.harvests.append(harvest)


class GardenDB(BaseModel):
    """Garden database containing all plants."""

    plants: Dict[str, Plant] = Field(
        default_factory=dict, description="Plants in the garden"
    )

    @classmethod
    def load_from_file(cls, file_path: Path) -> "GardenDB":
        """Load garden database from JSON file.

        A corrupt file is backed up and replaced with a fresh default DB
        rather than raising — this loads at import time, so an exception
        here would prevent the whole app from starting.
        """
        if not file_path.exists():
            # Create default database with initial plants
            garden_db = cls()
            garden_db.initialize_default_plants()
            return garden_db

        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            return cls(**data)
        except Exception as e:
            backup = file_path.with_suffix(".json.corrupt")
            logger.error(
                f"Garden DB file is unreadable ({e}); backing it up to {backup} "
                f"and starting with a fresh database"
            )
            try:
                os.replace(file_path, backup)
            except OSError as backup_err:
                logger.error(f"Failed to back up corrupt garden DB: {backup_err}")
            garden_db = cls()
            garden_db.initialize_default_plants()
            return garden_db

    def save_to_file(self, file_path: Path) -> None:
        """Save garden database to JSON file atomically (temp file + rename)."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = file_path.with_suffix(".json.tmp")
        with open(tmp_path, "w") as f:
            json.dump(self.model_dump(), f, indent=2, default=self._json_encoder)
        os.replace(tmp_path, file_path)

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

        harvest = Harvest(date=now_local(), yield_amount=yield_amount, notes=notes)
        plant.add_harvest(harvest)

    @staticmethod
    def _json_encoder(obj):
        """Custom JSON encoder for special types."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return str(obj)
        return obj
