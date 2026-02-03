"""Beeper Investigator entry point."""

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """Main entry point for the Beeper Investigator."""
    logger.info("Hello, Beeper Investigator!")
    logger.info("Beeper investigator starting up...")
    # Placeholder for investigator initialization
    # Future: Initialize LLM client, connect to Qdrant, start processing


if __name__ == "__main__":
    main()
