"""Repository CRD lookup for auto-PR generation.

Queries the Kubernetes API for Repository custom resources and
reads credential Secrets to enable git provider authentication.
"""

import base64
import logging
from dataclasses import dataclass

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)

_GROUP = "beeper.dev"
_VERSION = "v1"
_PLURAL = "repositories"


class CredentialError(Exception):
    """Raised when git credentials cannot be retrieved."""


@dataclass
class RepositoryInfo:
    """Parsed repository metadata from a Repository CRD."""

    name: str
    url: str
    provider: str
    credentials_secret: str
    base_branch: str = "main"
    pr_branch_prefix: str = "beeper/"
    require_pr: bool = True
    language: str | None = None
    linter: str | None = None
    test_command: str | None = None


class RepositoryLookup:
    """Finds Repository CRDs and reads credential Secrets."""

    def __init__(self) -> None:
        try:
            config.load_incluster_config()
        except config.ConfigException:
            logger.warning("In-cluster config not found, falling back to kubeconfig")
            config.load_kube_config()
        self._custom_api = client.CustomObjectsApi()
        self._core_api = client.CoreV1Api()

    def find_repository(
        self, service_name: str, namespace: str
    ) -> RepositoryInfo | None:
        """Find a connected Repository CRD matching the service.

        Searches Repository CRDs in the given namespace. Matches by
        metadata name containing the service name or spec.url containing
        it. Only returns repositories with status condition "connected".

        Args:
            service_name: Service name to match.
            namespace: Kubernetes namespace to search.

        Returns:
            RepositoryInfo if found, None otherwise.
        """
        try:
            result = self._custom_api.list_namespaced_custom_object(
                group=_GROUP,
                version=_VERSION,
                namespace=namespace,
                plural=_PLURAL,
            )
        except ApiException as exc:
            logger.warning(
                "Failed to list Repository CRDs in namespace %s: %s",
                namespace,
                exc.reason,
            )
            return None

        items = result.get("items", [])
        for item in items:
            status = item.get("status", {})
            condition = status.get("condition", "")
            if condition != "connected":
                continue

            metadata = item.get("metadata", {})
            spec = item.get("spec", {})
            name = metadata.get("name", "")
            url = spec.get("url", "")

            if service_name not in name and service_name not in url:
                continue

            branch_policy = spec.get("branch_policy", {}) or {}
            coding_standards = spec.get("coding_standards", {}) or {}

            return RepositoryInfo(
                name=name,
                url=url,
                provider=spec.get("provider", "github"),
                credentials_secret=spec.get("credentials_secret", ""),
                base_branch=branch_policy.get("base_branch", "main"),
                pr_branch_prefix=branch_policy.get("pr_branch_prefix", "beeper/"),
                require_pr=branch_policy.get("require_pr", True),
                language=coding_standards.get("language"),
                linter=coding_standards.get("linter"),
                test_command=coding_standards.get("test_command"),
            )

        logger.info("No connected Repository CRD found for service %s", service_name)
        return None

    def get_credentials(self, secret_name: str, namespace: str) -> str:
        """Read a git credential token from a Kubernetes Secret.

        Args:
            secret_name: Name of the K8s Secret.
            namespace: Namespace containing the Secret.

        Returns:
            Decoded token string.

        Raises:
            CredentialError: If Secret or token key is missing.
        """
        try:
            secret = self._core_api.read_namespaced_secret(secret_name, namespace)
        except ApiException as exc:
            raise CredentialError(
                f"Secret '{secret_name}' not found in namespace '{namespace}': {exc.reason}"
            ) from exc

        data = secret.data or {}
        token_b64 = data.get("token")
        if token_b64 is None:
            raise CredentialError(
                f"Secret '{secret_name}' does not contain a 'token' key"
            )

        return base64.b64decode(token_b64).decode("utf-8")
