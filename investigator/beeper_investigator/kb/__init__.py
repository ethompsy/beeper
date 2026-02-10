"""Beeper Knowledge Base client module.

This module provides the Qdrant client wrapper and Pydantic models
for interacting with the Beeper knowledge base.
"""

from beeper_investigator.kb.client import KBClient, get_kb_client
from beeper_investigator.kb.schemas import (
    InvestigationEntry,
    KnowledgeEntry,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "KBClient",
    "get_kb_client",
    "InvestigationEntry",
    "KnowledgeEntry",
]
