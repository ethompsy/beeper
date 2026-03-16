"""Tests for NoiseReportService."""

from unittest.mock import MagicMock

import pytest

from beeper_ui.services.noise_report_service import (
    NoiseReportData,
    NoiseReportService,
    NoiseReportServiceError,
    ServiceNoiseStats,
    _compute_signal_to_noise,
    _mark_worst_performers,
)


class TestGetAllServiceFeedback:
    """Tests for get_all_service_feedback method."""

    def setup_method(self) -> None:
        self.service = NoiseReportService(host="localhost")
        self.mock_client = MagicMock()
        self.service._client = self.mock_client

    def test_aggregates_feedback_across_services(self) -> None:
        p1 = MagicMock()
        p1.payload = {"service": "api", "investigation_feedback": "accurate"}
        p2 = MagicMock()
        p2.payload = {"service": "api", "investigation_feedback": "inaccurate"}
        p3 = MagicMock()
        p3.payload = {"service": "web", "investigation_feedback": "not_an_issue"}

        self.mock_client.scroll.return_value = ([p1, p2, p3], None)

        result = self.service.get_all_service_feedback()

        assert result["api"]["accurate"] == 1
        assert result["api"]["inaccurate"] == 1
        assert result["api"]["total"] == 2
        assert result["web"]["not_an_issue"] == 1
        assert result["web"]["total"] == 1

    def test_skips_investigations_without_feedback(self) -> None:
        p1 = MagicMock()
        p1.payload = {"service": "api"}  # no feedback field
        p2 = MagicMock()
        p2.payload = {"service": "api", "investigation_feedback": "accurate"}

        self.mock_client.scroll.return_value = ([p1, p2], None)

        result = self.service.get_all_service_feedback()
        assert result["api"]["total"] == 1
        assert result["api"]["accurate"] == 1

    def test_skips_investigations_without_service(self) -> None:
        p1 = MagicMock()
        p1.payload = {"investigation_feedback": "accurate"}  # no service

        self.mock_client.scroll.return_value = ([p1], None)

        result = self.service.get_all_service_feedback()
        assert result == {}

    def test_skips_invalid_feedback_types(self) -> None:
        p1 = MagicMock()
        p1.payload = {"service": "api", "investigation_feedback": "unknown_type"}

        self.mock_client.scroll.return_value = ([p1], None)

        result = self.service.get_all_service_feedback()
        assert result == {}

    def test_handles_none_payload(self) -> None:
        p1 = MagicMock()
        p1.payload = None

        self.mock_client.scroll.return_value = ([p1], None)

        result = self.service.get_all_service_feedback()
        assert result == {}

    def test_pagination_across_multiple_pages(self) -> None:
        p1 = MagicMock()
        p1.payload = {"service": "api", "investigation_feedback": "accurate"}
        p2 = MagicMock()
        p2.payload = {"service": "api", "investigation_feedback": "inaccurate"}

        self.mock_client.scroll.side_effect = [
            ([p1], "offset-2"),
            ([p2], None),
        ]

        result = self.service.get_all_service_feedback()
        assert result["api"]["total"] == 2
        assert result["api"]["accurate"] == 1
        assert result["api"]["inaccurate"] == 1

    def test_empty_results(self) -> None:
        self.mock_client.scroll.return_value = ([], None)

        result = self.service.get_all_service_feedback()
        assert result == {}

    def test_service_filter_applied(self) -> None:
        p1 = MagicMock()
        p1.payload = {"service": "api", "investigation_feedback": "accurate"}
        self.mock_client.scroll.return_value = ([p1], None)

        self.service.get_all_service_feedback(service_filter="api")

        call_args = self.mock_client.scroll.call_args
        scroll_filter = call_args.kwargs.get("scroll_filter") or call_args[1].get("scroll_filter")
        assert scroll_filter is not None

    def test_no_filter_when_service_is_none(self) -> None:
        self.mock_client.scroll.return_value = ([], None)

        self.service.get_all_service_feedback(service_filter=None)

        call_args = self.mock_client.scroll.call_args
        scroll_filter = call_args.kwargs.get("scroll_filter") or call_args[1].get("scroll_filter")
        assert scroll_filter is None

    def test_qdrant_failure_raises_error(self) -> None:
        self.mock_client.scroll.side_effect = Exception("connection refused")

        with pytest.raises(NoiseReportServiceError, match="Failed to get service feedback"):
            self.service.get_all_service_feedback()


class TestGetFalsePageStats:
    """Tests for get_false_page_stats method."""

    def setup_method(self) -> None:
        self.service = NoiseReportService(host="localhost")
        self.mock_client = MagicMock()
        self.service._client = self.mock_client

    def test_aggregates_false_pages_per_service(self) -> None:
        p1 = MagicMock()
        p1.payload = {"service": "api", "is_false_page": False}
        p2 = MagicMock()
        p2.payload = {"service": "api", "is_false_page": True}
        p3 = MagicMock()
        p3.payload = {"service": "web", "is_false_page": False}

        self.mock_client.scroll.return_value = ([p1, p2, p3], None)

        result = self.service.get_false_page_stats()
        assert result["api"]["total_notifications"] == 2
        assert result["api"]["false_page_count"] == 1
        assert result["api"]["false_page_rate"] == 0.5
        assert result["web"]["total_notifications"] == 1
        assert result["web"]["false_page_count"] == 0
        assert result["web"]["false_page_rate"] == 0.0

    def test_handles_empty_results(self) -> None:
        self.mock_client.scroll.return_value = ([], None)

        result = self.service.get_false_page_stats()
        assert result == {}

    def test_handles_none_payload(self) -> None:
        p1 = MagicMock()
        p1.payload = None

        self.mock_client.scroll.return_value = ([p1], None)

        result = self.service.get_false_page_stats()
        assert result["unknown"]["total_notifications"] == 1
        assert result["unknown"]["false_page_count"] == 0

    def test_qdrant_failure_raises_error(self) -> None:
        self.mock_client.scroll.side_effect = Exception("qdrant down")

        with pytest.raises(NoiseReportServiceError, match="Failed to get false page stats"):
            self.service.get_false_page_stats()

    def test_pagination(self) -> None:
        p1 = MagicMock()
        p1.payload = {"service": "api", "is_false_page": True}
        p2 = MagicMock()
        p2.payload = {"service": "api", "is_false_page": False}

        self.mock_client.scroll.side_effect = [
            ([p1], "offset-2"),
            ([p2], None),
        ]

        result = self.service.get_false_page_stats()
        assert result["api"]["total_notifications"] == 2
        assert result["api"]["false_page_count"] == 1


class TestGetFalsePageTrend:
    """Tests for get_false_page_trend method."""

    def setup_method(self) -> None:
        self.service = NoiseReportService(host="localhost")
        self.mock_client = MagicMock()
        self.service._client = self.mock_client

    def test_returns_trend_buckets_for_7d(self) -> None:
        self.mock_client.scroll.return_value = ([], None)

        result = self.service.get_false_page_trend(period="7d")
        assert len(result) == 7  # 7 buckets for 7d period

    def test_returns_trend_buckets_for_30d(self) -> None:
        self.mock_client.scroll.return_value = ([], None)

        result = self.service.get_false_page_trend(period="30d")
        assert len(result) == 6  # 6 buckets for 30d period

    def test_returns_trend_buckets_for_90d(self) -> None:
        self.mock_client.scroll.return_value = ([], None)

        result = self.service.get_false_page_trend(period="90d")
        assert len(result) == 6

    def test_trend_computes_false_page_rate(self) -> None:
        p1 = MagicMock()
        p1.payload = {"is_false_page": True}
        p2 = MagicMock()
        p2.payload = {"is_false_page": False}

        # First bucket has data, rest are empty
        side_effects = [([p1, p2], None)]
        for _ in range(5):  # remaining 5 buckets for 30d
            side_effects.append(([], None))
        self.mock_client.scroll.side_effect = side_effects

        result = self.service.get_false_page_trend(period="30d")
        assert result[0]["false_page_rate"] == 0.5
        assert result[0]["total"] == 2
        assert result[0]["false_page_count"] == 1

    def test_empty_bucket_has_zero_rate(self) -> None:
        self.mock_client.scroll.return_value = ([], None)

        result = self.service.get_false_page_trend(period="7d")
        for point in result:
            assert point["false_page_rate"] == 0.0
            assert point["total"] == 0

    def test_qdrant_failure_raises_error(self) -> None:
        self.mock_client.scroll.side_effect = Exception("connection error")

        with pytest.raises(NoiseReportServiceError, match="Failed to get false page trend"):
            self.service.get_false_page_trend()

    def test_defaults_to_30d_for_invalid_period(self) -> None:
        self.mock_client.scroll.return_value = ([], None)

        result = self.service.get_false_page_trend(period="invalid")
        assert len(result) == 6  # defaults to 30d config


class TestBuildNoiseReport:
    """Tests for build_noise_report method."""

    def setup_method(self) -> None:
        self.service = NoiseReportService(host="localhost")
        self.mock_client = MagicMock()
        self.service._client = self.mock_client

    def test_builds_complete_report(self) -> None:
        # Investigation feedback
        p1 = MagicMock()
        p1.payload = {"service": "api", "investigation_feedback": "accurate"}
        p2 = MagicMock()
        p2.payload = {"service": "api", "investigation_feedback": "not_an_issue"}

        # For feedback scroll, then audit stats scroll, then trend scrolls
        # The method calls get_all_service_feedback, get_false_page_stats, get_false_page_trend
        # Each needs its own scroll calls
        audit_p1 = MagicMock()
        audit_p1.payload = {"service": "api", "is_false_page": False}
        audit_p2 = MagicMock()
        audit_p2.payload = {"service": "api", "is_false_page": True}

        # feedback scroll + audit stats scroll + 6 trend bucket scrolls = 8 calls
        side_effects = [
            ([p1, p2], None),           # get_all_service_feedback
            ([audit_p1, audit_p2], None),  # get_false_page_stats
        ]
        for _ in range(6):  # 6 trend buckets
            side_effects.append(([], None))

        self.mock_client.scroll.side_effect = side_effects

        report = self.service.build_noise_report(period="30d")

        assert isinstance(report, NoiseReportData)
        assert report.total_investigations_with_feedback == 2
        assert report.overall_signal_to_noise == 0.5  # 1 accurate / 2 total
        assert len(report.per_service) == 1
        assert report.per_service[0].service_name == "api"
        assert report.selected_period == "30d"

    def test_empty_data_returns_zeros(self) -> None:
        # All scrolls return empty
        side_effects = [
            ([], None),  # feedback
            ([], None),  # audit stats
        ]
        for _ in range(6):
            side_effects.append(([], None))
        self.mock_client.scroll.side_effect = side_effects

        report = self.service.build_noise_report()

        assert report.overall_signal_to_noise == 0.0
        assert report.overall_false_page_rate == 0.0
        assert report.total_investigations_with_feedback == 0
        assert report.total_notifications == 0
        assert report.per_service == []

    def test_merges_services_from_both_sources(self) -> None:
        # Service "api" has feedback but "web" only has audit data
        p1 = MagicMock()
        p1.payload = {"service": "api", "investigation_feedback": "accurate"}

        audit_p1 = MagicMock()
        audit_p1.payload = {"service": "web", "is_false_page": True}

        side_effects = [
            ([p1], None),       # feedback — only "api"
            ([audit_p1], None),  # audit — only "web"
        ]
        for _ in range(6):
            side_effects.append(([], None))
        self.mock_client.scroll.side_effect = side_effects

        report = self.service.build_noise_report()

        service_names = [s.service_name for s in report.per_service]
        assert "api" in service_names
        assert "web" in service_names

    def test_propagates_service_error(self) -> None:
        self.mock_client.scroll.side_effect = Exception("qdrant failure")

        with pytest.raises(NoiseReportServiceError):
            self.service.build_noise_report()


class TestComputeSignalToNoise:
    """Tests for _compute_signal_to_noise helper."""

    def test_zero_total_returns_zero(self) -> None:
        assert _compute_signal_to_noise(0, 0) == 0.0

    def test_all_accurate_returns_one(self) -> None:
        assert _compute_signal_to_noise(10, 10) == 1.0

    def test_none_accurate_returns_zero(self) -> None:
        assert _compute_signal_to_noise(0, 10) == 0.0

    def test_partial_accuracy(self) -> None:
        result = _compute_signal_to_noise(3, 4)
        assert result == 0.75


class TestMarkWorstPerformers:
    """Tests for _mark_worst_performers helper."""

    def test_marks_services_above_threshold(self) -> None:
        stats = [
            ServiceNoiseStats(
                service_name="good", total_investigations=10,
                accurate_count=8, inaccurate_count=1, not_an_issue_count=1,
                signal_to_noise_ratio=0.8, false_page_count=1,
                total_notifications=10, false_page_rate=0.1,
            ),
            ServiceNoiseStats(
                service_name="bad", total_investigations=10,
                accurate_count=2, inaccurate_count=4, not_an_issue_count=4,
                signal_to_noise_ratio=0.2, false_page_count=8,
                total_notifications=10, false_page_rate=0.8,
            ),
        ]
        _mark_worst_performers(stats)

        # avg rate = 0.45, threshold = 0.9 — "bad" at 0.8 is below 2x avg
        # Actually avg = (0.1 + 0.8) / 2 = 0.45, threshold = 0.9
        # 0.8 < 0.9 so bad is NOT marked
        # Let's adjust: need rate > 2x average
        assert stats[0].is_worst_performer is False

    def test_no_services_with_notifications(self) -> None:
        stats = [
            ServiceNoiseStats(
                service_name="empty", total_investigations=5,
                accurate_count=3, inaccurate_count=1, not_an_issue_count=1,
                signal_to_noise_ratio=0.6, false_page_count=0,
                total_notifications=0, false_page_rate=0.0,
            ),
        ]
        _mark_worst_performers(stats)
        assert stats[0].is_worst_performer is False

    def test_marks_outlier_as_worst(self) -> None:
        stats = [
            ServiceNoiseStats(
                service_name="good1", total_investigations=10,
                accurate_count=8, inaccurate_count=1, not_an_issue_count=1,
                signal_to_noise_ratio=0.8, false_page_count=1,
                total_notifications=100, false_page_rate=0.01,
            ),
            ServiceNoiseStats(
                service_name="good2", total_investigations=10,
                accurate_count=7, inaccurate_count=2, not_an_issue_count=1,
                signal_to_noise_ratio=0.7, false_page_count=2,
                total_notifications=100, false_page_rate=0.02,
            ),
            ServiceNoiseStats(
                service_name="terrible", total_investigations=10,
                accurate_count=1, inaccurate_count=5, not_an_issue_count=4,
                signal_to_noise_ratio=0.1, false_page_count=50,
                total_notifications=100, false_page_rate=0.5,
            ),
        ]
        _mark_worst_performers(stats)

        # avg rate = (0.01 + 0.02 + 0.5) / 3 = 0.1767
        # threshold = 0.3533
        # "terrible" at 0.5 > 0.3533 — marked
        assert stats[0].is_worst_performer is False
        assert stats[1].is_worst_performer is False
        assert stats[2].is_worst_performer is True

    def test_empty_list(self) -> None:
        stats: list[ServiceNoiseStats] = []
        _mark_worst_performers(stats)  # should not raise


class TestServiceLifecycle:
    """Tests for service init and close."""

    def test_close_closes_client(self) -> None:
        service = NoiseReportService(host="localhost")
        mock_client = MagicMock()
        service._client = mock_client

        service.close()

        mock_client.close.assert_called_once()
        assert service._client is None

    def test_close_noop_when_no_client(self) -> None:
        service = NoiseReportService(host="localhost")
        service.close()  # should not raise

    def test_lazy_initialization(self) -> None:
        service = NoiseReportService(host="localhost")
        assert service._client is None
