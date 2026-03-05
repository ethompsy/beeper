"""Investigation CR status updater.

Updates the Investigation custom resource's status subresource
via the Kubernetes API. Only writes to the `message` field —
the `phase` lifecycle is owned by the operator controller.
"""

import logging

from kubernetes import client, config  # type: ignore[import-untyped]
from kubernetes.client.rest import ApiException  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Investigation CRD coordinates
_GROUP = "beeper.dev"
_VERSION = "v1"
_PLURAL = "investigations"


class InvestigationStatusUpdater:
    """Patches Investigation CR status with progress messages.

    Uses in-cluster ServiceAccount credentials (load_incluster_config).
    Falls back to kubeconfig for local development.
    """

    def __init__(self, investigation_id: str, namespace: str) -> None:
        self.investigation_id = investigation_id
        self.namespace = namespace

        try:
            config.load_incluster_config()
        except config.ConfigException:
            logger.warning("In-cluster config not found, falling back to kubeconfig")
            config.load_kube_config()

        self._api = client.CustomObjectsApi()

    def update_message(self, msg: str) -> bool:
        """Write a progress message to the Investigation CR status.

        Args:
            msg: Human-readable progress message.

        Returns:
            True if the update succeeded, False otherwise.
        """
        body = {"status": {"message": msg}}
        try:
            self._api.patch_namespaced_custom_object_status(
                group=_GROUP,
                version=_VERSION,
                namespace=self.namespace,
                plural=_PLURAL,
                name=self.investigation_id,
                body=body,
            )
            logger.debug("Updated Investigation status message: %s", msg)
            return True
        except ApiException as exc:
            logger.error(
                "Failed to update Investigation status message: %s (HTTP %s)",
                exc.reason,
                exc.status,
            )
            return False

    def set_completed(self, summary: str) -> None:
        """Mark investigation as completed with a summary.

        Note: Only sets the `message` field. The controller sets `phase`.

        Args:
            summary: Human-readable investigation summary.
        """
        self.update_message(f"Completed: {summary}")

    def set_failed(self, error: str) -> None:
        """Mark investigation as failed with an error description.

        Note: Only sets the `message` field. The controller sets `phase`.

        Args:
            error: Human-readable error description.
        """
        self.update_message(f"Failed: {error}")
