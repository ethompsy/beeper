"""Tests for NotificationAuditService."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.services.notification_audit_service import (
    AUDIT_COLLECTION,
    NotificationAuditService,
    NotificationAuditServiceError,
)


@pytest.fixture
def audit_service():
    """Create an audit service with a mocked Qdrant client."""
    svc = NotificationAuditService()
    mock_client = MagicMock()
    svc._qdrant_client = mock_client
    svc._collection_ensured = True
    yield svc
    svc.close()


@pytest.fixture
def sample_entry():
    """Sample outbox entry for testing."""
    return {
        "investigation_id": "inv-001",
        "event_type": "investigation_started",
        "severity": "high",
        "service": "payment-service",
        "payload": {
            "summary": "CPU spike detected",
            "evidence": ["CPU 95%", "Error rate 2.1%"],
            "confidence": 0.87,
        },
    }


@pytest.fixture
def sample_channel_config():
    """Sample channel config for testing."""
    return {
        "channel_type": "slack",
        "name": "ops-alerts",
        "config": {"channel": "#alerts"},
    }


@pytest.fixture
def sample_delivery_result():
    """Sample delivery result for testing."""
    return {
        "status": "delivered",
        "channel": "#alerts",
        "ts": "1234567890.123456",
    }


# --- record_audit tests ---


class TestRecordAudit:
    """Tests for NotificationAuditService.record_audit()."""

    def test_record_audit_creates_audit_record(
        self, audit_service, sample_entry, sample_channel_config, sample_delivery_result,
    ):
        """Audit record is created with correct fields."""
        audit_id = audit_service.record_audit(
            sample_entry, sample_channel_config, sample_delivery_result,
        )

        assert audit_id  # Non-empty UUID string
        uuid.UUID(audit_id)  # Valid UUID

        audit_service.qdrant_client.upsert.assert_called_once()
        call_args = audit_service.qdrant_client.upsert.call_args
        assert call_args.kwargs["collection_name"] == AUDIT_COLLECTION

        point = call_args.kwargs["points"][0]
        payload = point.payload
        assert payload["investigation_id"] == "inv-001"
        assert payload["event_type"] == "investigation_started"
        assert payload["severity"] == "high"
        assert payload["service"] == "payment-service"
        assert payload["channel_type"] == "slack"
        assert payload["channel_name"] == "ops-alerts"
        assert payload["delivery_status"] == "delivered"
        assert payload["delivery_error"] == ""
        assert payload["evidence_summary"] == ["CPU 95%", "Error rate 2.1%"]
        assert payload["confidence"] == 0.87
        assert payload["is_false_page"] is False
        assert payload["false_page_reason"] == ""
        assert payload["false_page_flagged_at"] == ""
        assert payload["timestamp"]  # Non-empty ISO timestamp

    def test_record_audit_with_failed_delivery(
        self, audit_service, sample_entry, sample_channel_config,
    ):
        """Audit record captures failed delivery status and error."""
        failed_result = {"status": "failed", "error": "Connection refused", "retryable": True}
        audit_service.record_audit(sample_entry, sample_channel_config, failed_result)

        point = audit_service.qdrant_client.upsert.call_args.kwargs["points"][0]
        assert point.payload["delivery_status"] == "failed"
        assert point.payload["delivery_error"] == "Connection refused"

    def test_record_audit_with_skipped_delivery(
        self, audit_service, sample_entry, sample_channel_config,
    ):
        """Audit record captures skipped delivery status."""
        skipped_result = {"status": "skipped", "error": "Channel type not supported"}
        audit_service.record_audit(sample_entry, sample_channel_config, skipped_result)

        point = audit_service.qdrant_client.upsert.call_args.kwargs["points"][0]
        assert point.payload["delivery_status"] == "skipped"

    def test_record_audit_with_pagerduty_channel(
        self, audit_service, sample_entry, sample_delivery_result,
    ):
        """Audit works with PagerDuty channel type."""
        pd_config = {"channel_type": "pagerduty", "name": "oncall-pd", "config": {}}
        audit_service.record_audit(sample_entry, pd_config, sample_delivery_result)

        point = audit_service.qdrant_client.upsert.call_args.kwargs["points"][0]
        assert point.payload["channel_type"] == "pagerduty"
        assert point.payload["channel_name"] == "oncall-pd"

    def test_record_audit_with_email_channel(
        self, audit_service, sample_entry, sample_delivery_result,
    ):
        """Audit works with email channel type."""
        email_config = {"channel_type": "email", "name": "team-email", "config": {}}
        audit_service.record_audit(sample_entry, email_config, sample_delivery_result)

        point = audit_service.qdrant_client.upsert.call_args.kwargs["points"][0]
        assert point.payload["channel_type"] == "email"

    def test_record_audit_with_webhook_channel(
        self, audit_service, sample_entry, sample_delivery_result,
    ):
        """Audit works with webhook channel type."""
        webhook_config = {"channel_type": "webhook", "name": "status-page", "config": {}}
        audit_service.record_audit(sample_entry, webhook_config, sample_delivery_result)

        point = audit_service.qdrant_client.upsert.call_args.kwargs["points"][0]
        assert point.payload["channel_type"] == "webhook"

    def test_record_audit_with_string_payload(
        self, audit_service, sample_channel_config, sample_delivery_result,
    ):
        """Handles string payload by parsing JSON."""
        entry = {
            "investigation_id": "inv-002",
            "event_type": "resolved",
            "severity": "low",
            "service": "api-gw",
            "payload": '{"evidence": ["Latency normalized"], "confidence": 0.95}',
        }
        audit_service.record_audit(entry, sample_channel_config, sample_delivery_result)

        point = audit_service.qdrant_client.upsert.call_args.kwargs["points"][0]
        assert point.payload["evidence_summary"] == ["Latency normalized"]
        assert point.payload["confidence"] == 0.95

    def test_record_audit_with_invalid_string_payload(
        self, audit_service, sample_channel_config, sample_delivery_result,
    ):
        """Handles invalid JSON string payload gracefully."""
        entry = {
            "investigation_id": "inv-003",
            "event_type": "investigation_started",
            "severity": "medium",
            "service": "svc",
            "payload": "not json",
        }
        audit_service.record_audit(entry, sample_channel_config, sample_delivery_result)

        point = audit_service.qdrant_client.upsert.call_args.kwargs["points"][0]
        assert point.payload["evidence_summary"] == []
        assert point.payload["confidence"] == 0.0

    def test_record_audit_with_missing_evidence(
        self, audit_service, sample_channel_config, sample_delivery_result,
    ):
        """Missing evidence in payload defaults to empty list."""
        entry = {
            "investigation_id": "inv-004",
            "event_type": "investigation_started",
            "severity": "high",
            "service": "svc",
            "payload": {"summary": "Alert fired"},
        }
        audit_service.record_audit(entry, sample_channel_config, sample_delivery_result)

        point = audit_service.qdrant_client.upsert.call_args.kwargs["points"][0]
        assert point.payload["evidence_summary"] == []

    def test_record_audit_with_none_delivery_error(
        self, audit_service, sample_entry, sample_channel_config,
    ):
        """None error in delivery result defaults to empty string."""
        result = {"status": "delivered", "error": None}
        audit_service.record_audit(sample_entry, sample_channel_config, result)

        point = audit_service.qdrant_client.upsert.call_args.kwargs["points"][0]
        assert point.payload["delivery_error"] == ""

    def test_record_audit_with_no_channel_name(
        self, audit_service, sample_entry, sample_delivery_result,
    ):
        """Missing channel name defaults to empty string."""
        config = {"channel_type": "slack", "config": {}}
        audit_service.record_audit(sample_entry, config, sample_delivery_result)

        point = audit_service.qdrant_client.upsert.call_args.kwargs["points"][0]
        assert point.payload["channel_name"] == ""

    def test_record_audit_raises_on_qdrant_error(
        self, audit_service, sample_entry, sample_channel_config, sample_delivery_result,
    ):
        """Raises NotificationAuditServiceError on Qdrant failure."""
        audit_service.qdrant_client.upsert.side_effect = Exception("Qdrant down")

        with pytest.raises(NotificationAuditServiceError, match="Failed to record audit"):
            audit_service.record_audit(sample_entry, sample_channel_config, sample_delivery_result)

    def test_record_audit_with_digest_deferred(
        self, audit_service, sample_entry, sample_channel_config,
    ):
        """Audit captures digest_deferred status."""
        result = {"status": "delivered", "mode": "digest_deferred"}
        audit_service.record_audit(sample_entry, sample_channel_config, result)

        point = audit_service.qdrant_client.upsert.call_args.kwargs["points"][0]
        assert point.payload["delivery_status"] == "delivered"

    def test_record_audit_with_non_numeric_confidence(
        self, audit_service, sample_channel_config, sample_delivery_result,
    ):
        """Non-numeric confidence defaults to 0.0."""
        entry = {
            "investigation_id": "inv-005",
            "event_type": "investigation_started",
            "severity": "high",
            "service": "svc",
            "payload": {"confidence": "not a number"},
        }
        audit_service.record_audit(entry, sample_channel_config, sample_delivery_result)

        point = audit_service.qdrant_client.upsert.call_args.kwargs["points"][0]
        assert point.payload["confidence"] == 0.0

    def test_record_audit_with_non_list_evidence(
        self, audit_service, sample_channel_config, sample_delivery_result,
    ):
        """Non-list evidence defaults to empty list."""
        entry = {
            "investigation_id": "inv-006",
            "event_type": "investigation_started",
            "severity": "high",
            "service": "svc",
            "payload": {"evidence": "single string"},
        }
        audit_service.record_audit(entry, sample_channel_config, sample_delivery_result)

        point = audit_service.qdrant_client.upsert.call_args.kwargs["points"][0]
        assert point.payload["evidence_summary"] == []


# --- flag_false_pages tests ---


class TestFlagFalsePages:
    """Tests for NotificationAuditService.flag_false_pages()."""

    def test_flag_false_pages_updates_matching_records(self, audit_service):
        """Flags all audit records for an investigation as false pages."""
        mock_point_1 = MagicMock()
        mock_point_1.id = "uuid-1"
        mock_point_2 = MagicMock()
        mock_point_2.id = "uuid-2"
        audit_service.qdrant_client.scroll.return_value = ([mock_point_1, mock_point_2], None)

        count = audit_service.flag_false_pages("inv-001", "false_positive")

        assert count == 2
        audit_service.qdrant_client.set_payload.assert_called_once()
        call_args = audit_service.qdrant_client.set_payload.call_args
        assert call_args.kwargs["collection_name"] == AUDIT_COLLECTION
        assert call_args.kwargs["payload"]["is_false_page"] is True
        assert call_args.kwargs["payload"]["false_page_reason"] == "false_positive"
        assert call_args.kwargs["payload"]["false_page_flagged_at"]  # ISO timestamp
        assert call_args.kwargs["points"] == ["uuid-1", "uuid-2"]

    def test_flag_false_pages_returns_zero_for_no_records(self, audit_service):
        """Returns 0 when no audit records exist for the investigation."""
        audit_service.qdrant_client.scroll.return_value = ([], None)

        count = audit_service.flag_false_pages("inv-999", "expected_behavior")

        assert count == 0
        audit_service.qdrant_client.set_payload.assert_not_called()

    def test_flag_false_pages_with_expected_behavior_reason(self, audit_service):
        """Flags with expected_behavior reason."""
        mock_point = MagicMock()
        mock_point.id = "uuid-3"
        audit_service.qdrant_client.scroll.return_value = ([mock_point], None)

        count = audit_service.flag_false_pages("inv-002", "expected_behavior")

        assert count == 1
        payload = audit_service.qdrant_client.set_payload.call_args.kwargs["payload"]
        assert payload["false_page_reason"] == "expected_behavior"

    def test_flag_false_pages_with_incorrect_accuracy_reason(self, audit_service):
        """Flags with incorrect_accuracy reason."""
        mock_point = MagicMock()
        mock_point.id = "uuid-4"
        audit_service.qdrant_client.scroll.return_value = ([mock_point], None)

        count = audit_service.flag_false_pages("inv-003", "incorrect_accuracy")

        assert count == 1
        payload = audit_service.qdrant_client.set_payload.call_args.kwargs["payload"]
        assert payload["false_page_reason"] == "incorrect_accuracy"

    def test_flag_false_pages_raises_on_scroll_error(self, audit_service):
        """Raises error when scroll fails."""
        audit_service.qdrant_client.scroll.side_effect = Exception("Connection lost")

        with pytest.raises(NotificationAuditServiceError, match="Failed to flag false pages"):
            audit_service.flag_false_pages("inv-001", "false_positive")

    def test_flag_false_pages_raises_on_set_payload_error(self, audit_service):
        """Raises error when set_payload fails."""
        mock_point = MagicMock()
        mock_point.id = "uuid-5"
        audit_service.qdrant_client.scroll.return_value = ([mock_point], None)
        audit_service.qdrant_client.set_payload.side_effect = Exception("Write failed")

        with pytest.raises(NotificationAuditServiceError, match="Failed to flag false pages"):
            audit_service.flag_false_pages("inv-001", "false_positive")

    def test_flag_false_pages_queries_by_investigation_id(self, audit_service):
        """Scroll filter uses investigation_id field condition."""
        audit_service.qdrant_client.scroll.return_value = ([], None)

        audit_service.flag_false_pages("inv-specific", "transient")

        call_args = audit_service.qdrant_client.scroll.call_args
        scroll_filter = call_args.kwargs["scroll_filter"]
        assert scroll_filter.must[0].key == "investigation_id"
        assert scroll_filter.must[0].match.value == "inv-specific"


# --- query_audit tests ---


class TestQueryAudit:
    """Tests for NotificationAuditService.query_audit()."""

    def _make_point(self, payload):
        mock_point = MagicMock()
        mock_point.payload = payload
        return mock_point

    def test_query_audit_returns_records(self, audit_service):
        """Returns audit records from Qdrant."""
        record = {"investigation_id": "inv-001", "service": "svc", "delivery_status": "delivered"}
        audit_service.qdrant_client.scroll.return_value = ([self._make_point(record)], None)

        results = audit_service.query_audit()

        assert len(results) == 1
        assert results[0]["investigation_id"] == "inv-001"

    def test_query_audit_with_service_filter(self, audit_service):
        """Applies service filter to scroll."""
        audit_service.qdrant_client.scroll.return_value = ([], None)

        audit_service.query_audit(service="payment-service")

        scroll_filter = audit_service.qdrant_client.scroll.call_args.kwargs["scroll_filter"]
        assert any(
            c.key == "service" and c.match.value == "payment-service"
            for c in scroll_filter.must
        )

    def test_query_audit_with_channel_type_filter(self, audit_service):
        """Applies channel_type filter."""
        audit_service.qdrant_client.scroll.return_value = ([], None)

        audit_service.query_audit(channel_type="slack")

        scroll_filter = audit_service.qdrant_client.scroll.call_args.kwargs["scroll_filter"]
        assert any(c.key == "channel_type" and c.match.value == "slack" for c in scroll_filter.must)

    def test_query_audit_with_date_range_filter(self, audit_service):
        """Applies date range filter using timestamp_epoch."""
        audit_service.qdrant_client.scroll.return_value = ([], None)

        audit_service.query_audit(date_from="2026-03-01T00:00:00Z", date_to="2026-03-14T23:59:59Z")

        scroll_filter = audit_service.qdrant_client.scroll.call_args.kwargs["scroll_filter"]
        range_condition = next(c for c in scroll_filter.must if c.key == "timestamp_epoch")
        assert isinstance(range_condition.range.gte, float)
        assert isinstance(range_condition.range.lte, float)
        assert range_condition.range.gte > 0
        assert range_condition.range.lte > range_condition.range.gte

    def test_query_audit_with_false_page_filter(self, audit_service):
        """Applies is_false_page filter."""
        audit_service.qdrant_client.scroll.return_value = ([], None)

        audit_service.query_audit(is_false_page=True)

        scroll_filter = audit_service.qdrant_client.scroll.call_args.kwargs["scroll_filter"]
        assert any(c.key == "is_false_page" and c.match.value is True for c in scroll_filter.must)

    def test_query_audit_with_no_filters(self, audit_service):
        """Queries without filters (scroll_filter is None)."""
        audit_service.qdrant_client.scroll.return_value = ([], None)

        audit_service.query_audit()

        assert audit_service.qdrant_client.scroll.call_args.kwargs["scroll_filter"] is None

    def test_query_audit_respects_limit(self, audit_service):
        """Limits results to requested count."""
        records = [self._make_point({"id": str(i)}) for i in range(5)]
        audit_service.qdrant_client.scroll.return_value = (records, None)

        results = audit_service.query_audit(limit=3)

        assert len(results) == 3

    def test_query_audit_max_limit_200(self, audit_service):
        """Limit is capped at 200."""
        audit_service.qdrant_client.scroll.return_value = ([], None)

        audit_service.query_audit(limit=500)

        # The internal limit+offset should not exceed 200
        call_args = audit_service.qdrant_client.scroll.call_args.kwargs
        assert call_args["limit"] <= 200

    def test_query_audit_empty_results(self, audit_service):
        """Returns empty list when no records match."""
        audit_service.qdrant_client.scroll.return_value = ([], None)

        results = audit_service.query_audit(service="nonexistent")

        assert results == []

    def test_query_audit_handles_qdrant_error(self, audit_service):
        """Returns empty list on Qdrant error."""
        audit_service.qdrant_client.scroll.side_effect = Exception("Qdrant error")

        results = audit_service.query_audit()

        assert results == []

    def test_query_audit_with_none_payload(self, audit_service):
        """Handles points with None payload."""
        mock_point = MagicMock()
        mock_point.payload = None
        audit_service.qdrant_client.scroll.return_value = ([mock_point], None)

        results = audit_service.query_audit()

        assert len(results) == 1
        assert results[0] == {}

    def test_query_audit_date_from_only(self, audit_service):
        """Applies date_from without date_to."""
        audit_service.qdrant_client.scroll.return_value = ([], None)

        audit_service.query_audit(date_from="2026-03-01T00:00:00Z")

        scroll_filter = audit_service.qdrant_client.scroll.call_args.kwargs["scroll_filter"]
        range_condition = next(c for c in scroll_filter.must if c.key == "timestamp_epoch")
        assert isinstance(range_condition.range.gte, float)
        assert range_condition.range.lte is None

    def test_query_audit_date_to_only(self, audit_service):
        """Applies date_to without date_from."""
        audit_service.qdrant_client.scroll.return_value = ([], None)

        audit_service.query_audit(date_to="2026-03-14T23:59:59Z")

        scroll_filter = audit_service.qdrant_client.scroll.call_args.kwargs["scroll_filter"]
        range_condition = next(c for c in scroll_filter.must if c.key == "timestamp_epoch")
        assert range_condition.range.gte is None
        assert isinstance(range_condition.range.lte, float)


# --- get_audit_statistics tests ---


class TestGetAuditStatistics:
    """Tests for NotificationAuditService.get_audit_statistics()."""

    def test_statistics_with_data(self, audit_service):
        """Returns correct statistics when data exists."""
        total_mock = MagicMock()
        total_mock.count = 100
        false_page_mock = MagicMock()
        false_page_mock.count = 15

        audit_service.qdrant_client.count.side_effect = [total_mock, false_page_mock]

        stats = audit_service.get_audit_statistics()

        assert stats["total_notifications"] == 100
        assert stats["false_page_count"] == 15
        assert stats["false_page_rate"] == 0.15

    def test_statistics_with_no_data(self, audit_service):
        """Returns zero values when no data exists."""
        zero_mock = MagicMock()
        zero_mock.count = 0

        audit_service.qdrant_client.count.side_effect = [zero_mock, zero_mock]

        stats = audit_service.get_audit_statistics()

        assert stats["total_notifications"] == 0
        assert stats["false_page_count"] == 0
        assert stats["false_page_rate"] == 0.0

    def test_statistics_division_by_zero(self, audit_service):
        """Handles zero total gracefully (no ZeroDivisionError)."""
        total_mock = MagicMock()
        total_mock.count = 0
        fp_mock = MagicMock()
        fp_mock.count = 0

        audit_service.qdrant_client.count.side_effect = [total_mock, fp_mock]

        stats = audit_service.get_audit_statistics()

        assert stats["false_page_rate"] == 0.0

    def test_statistics_with_service_filter(self, audit_service):
        """Applies service filter to statistics query."""
        total_mock = MagicMock()
        total_mock.count = 50
        fp_mock = MagicMock()
        fp_mock.count = 5

        audit_service.qdrant_client.count.side_effect = [total_mock, fp_mock]

        stats = audit_service.get_audit_statistics(service="payment-service")

        assert stats["total_notifications"] == 50
        # Verify both count calls used a filter
        assert audit_service.qdrant_client.count.call_count == 2
        call_args_list = audit_service.qdrant_client.count.call_args_list
        first_filter = call_args_list[0].kwargs["count_filter"]
        assert any(
            c.key == "service" and c.match.value == "payment-service"
            for c in first_filter.must
        )

    def test_statistics_with_channel_type_filter(self, audit_service):
        """Applies channel_type filter to statistics query."""
        total_mock = MagicMock()
        total_mock.count = 20
        fp_mock = MagicMock()
        fp_mock.count = 2

        audit_service.qdrant_client.count.side_effect = [total_mock, fp_mock]

        stats = audit_service.get_audit_statistics(channel_type="slack")

        assert stats["total_notifications"] == 20
        assert audit_service.qdrant_client.count.call_count == 2
        first_filter = audit_service.qdrant_client.count.call_args_list[0].kwargs["count_filter"]
        assert any(
            c.key == "channel_type" and c.match.value == "slack"
            for c in first_filter.must
        )

    def test_statistics_with_date_range(self, audit_service):
        """Applies date range filter to statistics query using timestamp_epoch."""
        total_mock = MagicMock()
        total_mock.count = 30
        fp_mock = MagicMock()
        fp_mock.count = 3

        audit_service.qdrant_client.count.side_effect = [total_mock, fp_mock]

        stats = audit_service.get_audit_statistics(
            date_from="2026-03-01T00:00:00Z", date_to="2026-03-14T23:59:59Z"
        )

        assert stats["total_notifications"] == 30
        assert stats["false_page_count"] == 3
        assert stats["false_page_rate"] == 0.1
        # Verify the filter uses timestamp_epoch with numeric range
        first_filter = audit_service.qdrant_client.count.call_args_list[0].kwargs["count_filter"]
        range_condition = next(c for c in first_filter.must if c.key == "timestamp_epoch")
        assert isinstance(range_condition.range.gte, float)

    def test_statistics_rate_rounding(self, audit_service):
        """Rate is rounded to 4 decimal places."""
        total_mock = MagicMock()
        total_mock.count = 3
        fp_mock = MagicMock()
        fp_mock.count = 1

        audit_service.qdrant_client.count.side_effect = [total_mock, fp_mock]

        stats = audit_service.get_audit_statistics()

        assert stats["false_page_rate"] == 0.3333

    def test_statistics_handles_qdrant_error(self, audit_service):
        """Returns zero stats on Qdrant error."""
        audit_service.qdrant_client.count.side_effect = Exception("Qdrant error")

        stats = audit_service.get_audit_statistics()

        assert stats["total_notifications"] == 0
        assert stats["false_page_count"] == 0
        assert stats["false_page_rate"] == 0.0


# --- _ensure_collection tests ---


class TestEnsureCollection:
    """Tests for collection auto-creation."""

    def test_ensure_collection_creates_if_not_exists(self):
        """Creates collection when get_collection raises."""
        svc = NotificationAuditService()
        mock_client = MagicMock()
        svc._qdrant_client = mock_client
        mock_client.get_collection.side_effect = Exception("Not found")

        svc._ensure_collection()

        mock_client.create_collection.assert_called_once()
        assert svc._collection_ensured is True
        svc.close()

    def test_ensure_collection_skips_if_exists(self):
        """Does not create collection when it already exists."""
        svc = NotificationAuditService()
        mock_client = MagicMock()
        svc._qdrant_client = mock_client

        svc._ensure_collection()

        mock_client.create_collection.assert_not_called()
        assert svc._collection_ensured is True
        svc.close()

    def test_ensure_collection_cached(self):
        """Does not check again after first success."""
        svc = NotificationAuditService()
        mock_client = MagicMock()
        svc._qdrant_client = mock_client
        svc._collection_ensured = True

        svc._ensure_collection()

        mock_client.get_collection.assert_not_called()
        svc.close()

    def test_ensure_collection_handles_create_failure(self):
        """Logs warning when collection creation fails."""
        svc = NotificationAuditService()
        mock_client = MagicMock()
        svc._qdrant_client = mock_client
        mock_client.get_collection.side_effect = Exception("Not found")
        mock_client.create_collection.side_effect = Exception("Create failed")

        svc._ensure_collection()

        assert svc._collection_ensured is False
        svc.close()


# --- Lazy client initialization tests ---


class TestClientInitialization:
    """Tests for lazy Qdrant client initialization."""

    @patch("beeper_ui.services.notification_audit_service.QdrantClient")
    def test_lazy_qdrant_client_creation(self, mock_qdrant_cls):
        """Qdrant client is created on first access."""
        svc = NotificationAuditService()
        _ = svc.qdrant_client

        mock_qdrant_cls.assert_called_once_with(host="localhost", port=6333)
        svc.close()

    @patch.dict("os.environ", {"QDRANT_HOST": "qdrant.local", "QDRANT_PORT": "6334"})
    @patch("beeper_ui.services.notification_audit_service.QdrantClient")
    def test_qdrant_client_uses_env_vars(self, mock_qdrant_cls):
        """Qdrant client respects QDRANT_HOST and QDRANT_PORT env vars."""
        svc = NotificationAuditService()
        _ = svc.qdrant_client

        mock_qdrant_cls.assert_called_once_with(host="qdrant.local", port=6334)
        svc.close()

    def test_close_cleans_up_client(self):
        """Close cleans up the Qdrant client."""
        svc = NotificationAuditService()
        mock_client = MagicMock()
        svc._qdrant_client = mock_client

        svc.close()

        mock_client.close.assert_called_once()
        assert svc._qdrant_client is None
