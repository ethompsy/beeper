"""Beeper Investigator entry point.

This module is the main entry point for investigator Jobs spawned by the operator.
It reads configuration from environment variables set by the K8s Job spec.
"""

import json
import logging
import os
import sys
from typing import Any

from beeper_investigator.kb.client import KBClient
from beeper_investigator.llm.client import LlmClient, LlmClientError


class JsonFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def __init__(self, investigation_id: str) -> None:
        """Initialize formatter with investigation context.

        Args:
            investigation_id: The investigation ID to include in all log records.
        """
        super().__init__()
        self.investigation_id = investigation_id

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: The log record to format.

        Returns:
            JSON-formatted log string.
        """
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "investigation_id": self.investigation_id,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Include exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def configure_logging(investigation_id: str) -> logging.Logger:
    """Configure structured JSON logging with investigation context.

    Args:
        investigation_id: The investigation ID to include in all logs.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger("beeper_investigator")
    logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Add JSON formatter to stdout handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(investigation_id))
    logger.addHandler(handler)

    return logger


def get_required_env(name: str) -> str:
    """Get a required environment variable.

    Args:
        name: Environment variable name.

    Returns:
        The environment variable value.

    Raises:
        SystemExit: If the variable is not set.
    """
    value = os.environ.get(name)
    if not value:
        print(
            json.dumps(
                {
                    "level": "ERROR",
                    "message": f"Required environment variable {name} is not set",
                }
            ),
            file=sys.stderr,
        )
        sys.exit(1)
    return value


def main() -> None:
    """Main entry point for the Beeper Investigator.

    Reads configuration from environment variables:
    - INVESTIGATION_ID: The Investigation CR name (required)
    - INVESTIGATION_NAMESPACE: The namespace (required)
    - BEEPER_LLM_PROVIDER: LLM provider (required)
    - BEEPER_LLM_MODEL: LLM model name (required)
    - BEEPER_LLM_API_KEY: LLM API key (required for cloud providers)
    - QDRANT_HOST: Qdrant server host (optional, defaults to localhost)
    - QDRANT_PORT: Qdrant server port (optional, defaults to 6333)

    Exit codes:
    - 0: Investigation completed successfully
    - 1: Investigation failed
    """
    # Get required environment variables
    investigation_id = get_required_env("INVESTIGATION_ID")
    investigation_namespace = get_required_env("INVESTIGATION_NAMESPACE")

    # Configure structured logging with investigation context
    logger = configure_logging(investigation_id)

    logger.info(
        "Starting investigation in namespace %s",
        investigation_namespace,
    )

    try:
        # Initialize LLM client from environment
        logger.info("Initializing LLM client")
        llm_client = LlmClient.from_env()
        logger.info(
            f"LLM client initialized: provider={llm_client.provider}, model={llm_client.model}"
        )

        # Initialize Qdrant KB client from environment
        logger.info("Initializing Qdrant KB client")
        kb_client = KBClient()

        # Verify Qdrant connectivity
        if not kb_client.health_check():
            logger.error("Failed to connect to Qdrant")
            sys.exit(1)
        logger.info(f"Connected to Qdrant at {kb_client.host}:{kb_client.port}")

        # TODO: Implement investigation logic in future stories
        # - Fetch alert details
        # - Query knowledge base
        # - Generate analysis with LLM
        # - Store findings

        logger.info("Investigation completed successfully")
        sys.exit(0)

    except LlmClientError as e:
        logger.error(f"LLM client error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Investigation failed with unexpected error: {e}")
        sys.exit(1)
    finally:
        # Cleanup
        if "kb_client" in locals():
            kb_client.close()


if __name__ == "__main__":
    main()
