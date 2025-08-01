"""
Pydantic models for email sink data structures.
"""

from datetime import datetime
from typing import Dict, Any
from pydantic import BaseModel, Field


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


class AlertRequest(BaseModel):
    """Request model for posting alerts to internal endpoints."""

    uid: str
    subject: str
    body: str
    sender: str
    date: datetime
    alert_type: str = Field(default="email", description="Type of alert")
