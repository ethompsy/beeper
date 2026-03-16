"""Pydantic models for Beeper KB entities.

These schemas define the structure of entries stored in Qdrant collections.
Field names use snake_case per architecture standards.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class InvestigationStatus(str, Enum):
    """Status of an investigation."""

    ACTIVE = "active"
    RESOLVED = "resolved"
    STALE = "stale"


class KnowledgeEntryType(str, Enum):
    """Type of knowledge base entry."""

    INVESTIGATION = "investigation"
    RUNBOOK = "runbook"
    CORRECTION = "correction"
    PROVEN_FIX = "proven_fix"


class InvestigationEntry(BaseModel):
    """Schema for investigation entries in Qdrant.

    Maps to the 'investigations' collection payload structure.
    """

    investigation_id: str = Field(..., description="Unique investigation identifier")
    status: InvestigationStatus = Field(..., description="Investigation status")
    started_at: datetime = Field(..., description="When investigation started (ISO 8601)")
    service: str = Field(..., description="Affected service name")
    title: Optional[str] = Field(None, description="Investigation title")
    root_cause: Optional[str] = Field(None, description="Identified root cause")
    resolution: Optional[str] = Field(None, description="Resolution applied")

    model_config = ConfigDict(use_enum_values=True)


class KnowledgeEntry(BaseModel):
    """Schema for knowledge base entries in Qdrant.

    Maps to the 'knowledge' collection payload structure.
    """

    entry_id: str = Field(..., description="Unique entry identifier")
    entry_type: KnowledgeEntryType = Field(..., description="Entry type")
    service: str = Field(..., description="Related service name")
    created_at: datetime = Field(..., description="When entry was created (ISO 8601)")
    title: str = Field(..., description="Entry title")
    content: str = Field(..., description="Entry content (markdown)")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    version: int = Field(default=1, description="Entry version number")

    model_config = ConfigDict(use_enum_values=True)


class SearchResult(BaseModel):
    """Result from a vector similarity search."""

    id: str = Field(..., description="Point ID in Qdrant")
    score: float = Field(..., description="Similarity score (0-1 for cosine)")
    payload: dict[str, Any] = Field(..., description="Point payload data")


class CollectionInfo(BaseModel):
    """Information about a Qdrant collection."""

    name: str = Field(..., description="Collection name")
    vectors_count: int = Field(..., description="Number of vectors in collection")
    points_count: int = Field(..., description="Number of points in collection")
