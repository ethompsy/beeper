"""Tests for InvestigationStatusUpdater."""

from unittest.mock import MagicMock, patch

from beeper_investigator.k8s.status import InvestigationStatusUpdater


class TestInvestigationStatusUpdater:
    """Tests for the K8s status updater."""

    @patch("beeper_investigator.k8s.status.config")
    @patch("beeper_investigator.k8s.status.client")
    def _make_updater(
        self, mock_client: MagicMock, mock_config: MagicMock
    ) -> tuple[InvestigationStatusUpdater, MagicMock]:
        """Helper: create an updater with mocked K8s client."""
        mock_api = MagicMock()
        mock_client.CustomObjectsApi.return_value = mock_api
        updater = InvestigationStatusUpdater("inv-test-123", "production")
        return updater, mock_api

    def test_update_message_patches_status(self) -> None:
        """update_message() PATCHes the Investigation CR status subresource."""
        updater, mock_api = self._make_updater()

        updater.update_message("Correlating signals...")

        mock_api.patch_namespaced_custom_object_status.assert_called_once_with(
            group="beeper.dev",
            version="v1",
            namespace="production",
            plural="investigations",
            name="inv-test-123",
            body={"status": {"message": "Correlating signals..."}},
        )

    def test_set_completed_includes_prefix(self) -> None:
        """set_completed() writes 'Completed: <summary>' message."""
        updater, mock_api = self._make_updater()

        updater.set_completed("Root cause identified: memory leak in cache layer")

        call_body = mock_api.patch_namespaced_custom_object_status.call_args.kwargs["body"]
        assert call_body["status"]["message"] == (
            "Completed: Root cause identified: memory leak in cache layer"
        )

    def test_set_failed_includes_prefix(self) -> None:
        """set_failed() writes 'Failed: <error>' message."""
        updater, mock_api = self._make_updater()

        updater.set_failed("Timed out querying Prometheus")

        call_body = mock_api.patch_namespaced_custom_object_status.call_args.kwargs["body"]
        assert call_body["status"]["message"] == "Failed: Timed out querying Prometheus"

    @patch("beeper_investigator.k8s.status.config")
    @patch("beeper_investigator.k8s.status.client")
    def test_api_error_logged_not_raised(
        self, mock_client: MagicMock, mock_config: MagicMock
    ) -> None:
        """ApiException from K8s is logged but does not raise."""
        from kubernetes.client.rest import ApiException

        mock_api = MagicMock()
        mock_api.patch_namespaced_custom_object_status.side_effect = ApiException(
            status=403, reason="Forbidden"
        )
        mock_client.CustomObjectsApi.return_value = mock_api

        updater = InvestigationStatusUpdater("inv-err", "default")
        # Should not raise
        updater.update_message("test")

    @patch("beeper_investigator.k8s.status.config")
    @patch("beeper_investigator.k8s.status.client")
    def test_uses_incluster_config(
        self, mock_client: MagicMock, mock_config: MagicMock
    ) -> None:
        """Constructor tries load_incluster_config first."""
        InvestigationStatusUpdater("inv-001", "ns")
        mock_config.load_incluster_config.assert_called_once()
