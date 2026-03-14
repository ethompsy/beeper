"""Beeper Investigator entry point.

This module is the main entry point for investigator Jobs spawned by the operator.
It reads configuration from environment variables set by the K8s Job spec.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from beeper_investigator.agent import InvestigatorAgent, LlmUnavailableError, SourceClients
from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.kb.client import KBClient
from beeper_investigator.llm.client import LlmClient, LlmClientError
from beeper_investigator.sources.loki import LokiClient
from beeper_investigator.sources.prometheus import PrometheusClient


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
    - PROMETHEUS_URL: Prometheus server URL (optional)
    - LOKI_URL: Loki server URL (optional)

    Exit codes:
    - 0: Investigation completed successfully
    - 1: Investigation failed (permanent — non-retryable)
    - 2: Investigation failed (retryable — LLM unavailable, K8s Job will retry)
    """
    # Build investigation context from environment
    context = InvestigationContext.from_env()

    # Configure structured logging with investigation context
    logger = configure_logging(context.investigation_id)

    logger.info(
        "Starting investigation %s in namespace %s",
        context.investigation_id,
        context.namespace,
    )

    kb_client: KBClient | None = None
    sources = SourceClients()

    try:
        # Initialize LLM client from environment
        logger.info("Initializing LLM client")
        llm_client = LlmClient.from_env()
        logger.info(
            "LLM client initialized: provider=%s, model=%s",
            llm_client.provider,
            llm_client.model,
        )

        # Initialize Qdrant KB client from environment
        logger.info("Initializing Qdrant KB client")
        kb_client = KBClient()

        # Initialize optional source clients
        prom_url = os.environ.get("PROMETHEUS_URL", "")
        if prom_url:
            sources.prometheus = PrometheusClient(base_url=prom_url)
            logger.info("Prometheus source configured: %s", prom_url)

        loki_url = os.environ.get("LOKI_URL", "")
        if loki_url:
            sources.loki = LokiClient(base_url=loki_url)
            logger.info("Loki source configured: %s", loki_url)

        # Initialize K8s status updater
        status_updater = InvestigationStatusUpdater(
            context.investigation_id, context.namespace
        )

        # Build and run agent
        agent = InvestigatorAgent(
            context=context,
            kb_client=kb_client,
            llm_client=llm_client,
            sources=sources,
            status_updater=status_updater,
        )

        result = agent.run()

        if result.success:
            logger.info("Investigation completed successfully: %s", result.summary)
            sys.exit(0)
        else:
            logger.error("Investigation failed: %s", result.error or result.summary)
            sys.exit(1)

    except LlmUnavailableError as e:
        # Emit structured escalation event (NFR15: human escalation within 60s)
        logger.error(
            json.dumps({
                "event": "llm_escalation",
                "investigation_id": context.investigation_id,
                "error": str(e),
                "escalation_type": "human_required",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        )
        # Exit code 2 = retryable failure — K8s Job controller will retry
        sys.exit(2)
    except LlmClientError as e:
        logger.error("LLM client error: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.exception("Investigation failed with unexpected error: %s", e)
        sys.exit(1)
    finally:
        # Cleanup
        if kb_client is not None:
            kb_client.close()
        if sources.prometheus is not None:
            sources.prometheus.close()
        if sources.loki is not None:
            sources.loki.close()


if __name__ == "__main__":
    main()
