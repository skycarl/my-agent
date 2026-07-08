"""
Pydantic models for email sink data structures.
"""

from datetime import datetime
from typing import Dict, Any
from pydantic import BaseModel, Field

# Re-exported so the sink and server share one definition of the wire contract.
from app.models.tasks import AlertRequest as AlertRequest


class EmailAlert(BaseModel):
    """Model for a parsed email alert."""

    uid: str = Field(description="Unique identifier from email server")
    subject: str = Field(description="Email subject line")
    body: str = Field(description="Email body content (plain text)")
    sender: str = Field(description="Email sender address")
    date: datetime = Field(description="Email date/time")
    raw_headers: Dict[str, Any] = Field(
        default_factory=dict, description="Raw email headers"
    )


class EmailSinkConfig(BaseModel):
    """Configuration for email monitoring routing."""

    sender_pattern: str = Field(
        description="Email pattern to match (can be full address or domain)"
    )
    endpoint: str = Field(description="Internal API endpoint to POST alerts to")
    description: str = Field(description="Human-readable description of this sink")
