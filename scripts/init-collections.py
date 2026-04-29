#!/usr/bin/env python3
"""Initialize Qdrant collections for Beeper.

This script creates the 'investigations' and 'knowledge' collections
with the correct schemas and payload indexes for filtering.

Usage:
    python scripts/init-collections.py [--host HOST] [--port PORT] [--vector-dim DIM]

Environment variables:
    QDRANT_HOST: Qdrant server host (default: localhost)
    QDRANT_PORT: Qdrant server port (default: 6333)
    VECTOR_DIMENSION: Embedding vector dimension (default: 1536)
"""

import argparse
import logging
import os
import sys

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Collection configurations
COLLECTIONS = {
    "investigations": {
        "description": "Active and historical investigation state",
        "payload_indexes": [
            ("investigation_id", PayloadSchemaType.KEYWORD),
            ("status", PayloadSchemaType.KEYWORD),
            ("service", PayloadSchemaType.KEYWORD),
            ("started_at", PayloadSchemaType.DATETIME),
        ],
    },
    "knowledge": {
        "description": "Knowledge base entries (investigations, runbooks, corrections)",
        "payload_indexes": [
            ("entry_id", PayloadSchemaType.KEYWORD),
            ("entry_type", PayloadSchemaType.KEYWORD),
            ("service", PayloadSchemaType.KEYWORD),
            ("created_at", PayloadSchemaType.DATETIME),
            ("source_investigation_id", PayloadSchemaType.KEYWORD),
            ("contributing_investigations", PayloadSchemaType.KEYWORD),
        ],
    },
    "knowledge_versions": {
        "description": "Version history for knowledge base entries",
        "vector_dim": 1,  # No semantic search needed; use minimal dummy vector
        "payload_indexes": [
            ("entry_id", PayloadSchemaType.KEYWORD),
            ("version", PayloadSchemaType.INTEGER),
        ],
    },
    "learning_patterns": {
        "description": "Learning patterns from correction diffs",
        "vector_dim": 1,  # No semantic search needed; payload-only points
        "payload_indexes": [
            ("pattern_id", PayloadSchemaType.KEYWORD),
            ("entry_id", PayloadSchemaType.KEYWORD),
            ("correction_id", PayloadSchemaType.KEYWORD),
            ("service_name", PayloadSchemaType.KEYWORD),
            ("category", PayloadSchemaType.KEYWORD),
        ],
    },
    "service_trust_levels": {
        "description": "Per-service trust levels for graduated authoring",
        "vector_dim": 1,  # No semantic search needed; payload-only points
        "payload_indexes": [
            ("service_name", PayloadSchemaType.KEYWORD),
            ("trust_level", PayloadSchemaType.KEYWORD),
        ],
    },
}


def create_collection(
    client: QdrantClient, name: str, config: dict, vector_dim: int
) -> bool:
    """Create a collection if it doesn't exist.

    Args:
        client: Qdrant client instance
        name: Collection name
        config: Collection configuration dict
        vector_dim: Vector dimension for embeddings

    Returns:
        True if collection was created, False if it already existed
    """
    # Check if collection exists
    try:
        existing = client.get_collection(name)
        logger.info(
            f"Collection '{name}' already exists (points: {existing.points_count})"
        )
        return False
    except UnexpectedResponse:
        pass  # Collection doesn't exist, create it

    # Create collection (use per-collection vector_dim if specified)
    col_vector_dim = config.get("vector_dim", vector_dim)
    logger.info(f"Creating collection '{name}' with vector dimension {col_vector_dim}")
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=col_vector_dim, distance=Distance.COSINE),
    )

    # Create payload indexes for efficient filtering
    for field_name, field_type in config["payload_indexes"]:
        logger.info(f"  Creating payload index: {field_name} ({field_type})")
        client.create_payload_index(
            collection_name=name,
            field_name=field_name,
            field_schema=field_type,
        )

    logger.info(f"Collection '{name}' created successfully")
    return True


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Initialize Qdrant collections for Beeper")
    parser.add_argument(
        "--host",
        default=os.getenv("QDRANT_HOST", "localhost"),
        help="Qdrant server host (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("QDRANT_PORT", "6333")),
        help="Qdrant server port (default: 6333)",
    )
    parser.add_argument(
        "--vector-dim",
        type=int,
        default=int(os.getenv("VECTOR_DIMENSION", "1536")),
        help="Embedding vector dimension (default: 1536)",
    )
    args = parser.parse_args()

    logger.info(f"Connecting to Qdrant at {args.host}:{args.port}")

    try:
        client = QdrantClient(host=args.host, port=args.port)

        # Verify connection
        client.get_collections()
        logger.info("Connected to Qdrant successfully")

    except Exception as e:
        logger.error(f"Failed to connect to Qdrant: {e}")
        return 1

    # Create collections
    created_count = 0
    for name, config in COLLECTIONS.items():
        try:
            if create_collection(client, name, config, args.vector_dim):
                created_count += 1
        except Exception as e:
            logger.error(f"Failed to create collection '{name}': {e}")
            return 1

    logger.info(f"Initialization complete. Created {created_count} new collection(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
