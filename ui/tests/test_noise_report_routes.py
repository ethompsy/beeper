"""Tests for noise report dashboard routes."""

from unittest.mock import MagicMock, patch

from beeper_ui.services.noise_report_service import (
    NoiseReportData,
    NoiseReportServiceError,
    ServiceNoiseStats,
)

REPORT_SVC_PATCH = "beeper_ui.routes.reports._get_noise_report_service"


def _make_service_stats(
    name: str = "api-gateway",
    total: int = 20,
    accurate: int = 15,
    inaccurate: int = 3,
    not_an_issue: int = 2,
    false_page_count: int = 5,
    total_notifications: int = 50,
    is_worst: bool = False,
) -> ServiceNoiseStats:
    sn = accurate / total if total > 0 else 0.0
    fp_rate = false_page_count / total_notifications if total_notifications > 0 else 0.0
    return ServiceNoiseStats(
        service_name=name,
        total_investigations=total,
        accurate_count=accurate,
        inaccurate_count=inaccurate,
        not_an_issue_count=not_an_issue,
        signal_to_noise_ratio=round(sn, 4),
        false_page_count=false_page_count,
        total_notifications=total_notifications,
        false_page_rate=round(fp_rate, 4),
        is_worst_performer=is_worst,
    )


def _make_report(
    per_service: list[ServiceNoiseStats] | None = None,
) -> NoiseReportData:
    services = per_service or [_make_service_stats()]
    total_feedback = sum(s.total_investigations for s in services)
    total_accurate = sum(s.accurate_count for s in services)
    total_notif = sum(s.total_notifications for s in services)
    total_fp = sum(s.false_page_count for s in services)
    return NoiseReportData(
        overall_signal_to_noise=(
            round(total_accurate / total_feedback, 4) if total_feedback > 0 else 0.0
        ),
        overall_false_page_rate=(
            round(total_fp / total_notif, 4) if total_notif > 0 else 0.0
        ),
        total_investigations_with_feedback=total_feedback,
        total_notifications=total_notif,
        total_false_pages=total_fp,
        per_service=services,
        trend_data=[
            {"period_label": "Mar 01", "false_page_rate": 0.1, "total": 10, "false_page_count": 1},
            {"period_label": "Mar 06", "false_page_rate": 0.05, "total": 20, "false_page_count": 1},
        ],
        selected_service=None,
        selected_period="30d",
    )


class TestNoiseReportRoute:
    """Tests for GET /reports/noise."""

    def test_returns_200_for_user_role(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.return_value = _make_report()
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            resp = user_client.get("/reports/noise")
        assert resp.status_code == 200

    def test_returns_200_for_admin_role(self, admin_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.return_value = _make_report()
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            resp = admin_client.get("/reports/noise")
        assert resp.status_code == 200

    def test_renders_full_page(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.return_value = _make_report()
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            resp = user_client.get("/reports/noise")
        html = resp.data.decode()
        assert "<!DOCTYPE html>" in html
        assert "Noise Report" in html

    def test_htmx_returns_partial(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.return_value = _make_report()
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            resp = user_client.get(
                "/reports/noise",
                headers={"HX-Request": "true"},
            )
        html = resp.data.decode()
        assert resp.status_code == 200
        assert "<!DOCTYPE html>" not in html
        assert "Signal-to-Noise Ratio" in html

    def test_renders_summary_cards(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.return_value = _make_report()
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            resp = user_client.get("/reports/noise")
        html = resp.data.decode()
        assert "Signal-to-Noise Ratio" in html
        assert "False Page Rate" in html
        assert "Investigations with Feedback" in html
        assert "Total Notifications" in html

    def test_renders_per_service_table(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.return_value = _make_report()
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            resp = user_client.get("/reports/noise")
        html = resp.data.decode()
        assert "api-gateway" in html
        assert "Per-Service Breakdown" in html

    def test_highlights_worst_performer(self, user_client) -> None:
        stats = [
            _make_service_stats("good-svc"),
            _make_service_stats("bad-svc", is_worst=True),
        ]
        mock_svc = MagicMock()
        mock_svc.build_noise_report.return_value = _make_report(per_service=stats)
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            resp = user_client.get("/reports/noise")
        html = resp.data.decode()
        assert "noise-worst-performer" in html

    def test_renders_trend_data(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.return_value = _make_report()
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            resp = user_client.get("/reports/noise")
        html = resp.data.decode()
        assert "False Page Rate Trend" in html
        assert "Mar 01" in html

    def test_service_filter_passed_to_service(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.return_value = _make_report()
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            user_client.get("/reports/noise?service=api-gateway")
        mock_svc.build_noise_report.assert_called_once_with(
            service="api-gateway", period="30d"
        )

    def test_period_filter_passed_to_service(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.return_value = _make_report()
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            user_client.get("/reports/noise?period=7d")
        mock_svc.build_noise_report.assert_called_once_with(
            service=None, period="7d"
        )

    def test_invalid_period_defaults_to_30d(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.return_value = _make_report()
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            user_client.get("/reports/noise?period=invalid")
        mock_svc.build_noise_report.assert_called_once_with(
            service=None, period="30d"
        )

    def test_invalid_service_name_ignored(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.return_value = _make_report()
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            user_client.get("/reports/noise?service=<script>alert(1)</script>")
        mock_svc.build_noise_report.assert_called_once_with(
            service=None, period="30d"
        )

    def test_service_close_called(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.return_value = _make_report()
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            user_client.get("/reports/noise")
        mock_svc.close.assert_called_once()

    def test_service_close_called_on_error(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.side_effect = NoiseReportServiceError("qdrant down")
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            resp = user_client.get("/reports/noise")
        assert resp.status_code == 200
        mock_svc.close.assert_called_once()

    def test_error_renders_error_message(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.side_effect = NoiseReportServiceError("qdrant down")
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            resp = user_client.get("/reports/noise")
        html = resp.data.decode()
        assert "Unable to load noise report data" in html

    def test_error_htmx_returns_partial(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.side_effect = NoiseReportServiceError("fail")
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            resp = user_client.get(
                "/reports/noise",
                headers={"HX-Request": "true"},
            )
        html = resp.data.decode()
        assert "<!DOCTYPE html>" not in html
        assert "Unable to load noise report data" in html

    def test_empty_service_param_treated_as_none(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.return_value = _make_report()
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            user_client.get("/reports/noise?service=")
        mock_svc.build_noise_report.assert_called_once_with(
            service=None, period="30d"
        )

    def test_empty_report_shows_empty_state(self, user_client) -> None:
        empty_report = NoiseReportData(
            overall_signal_to_noise=0.0,
            overall_false_page_rate=0.0,
            total_investigations_with_feedback=0,
            total_notifications=0,
            total_false_pages=0,
            per_service=[],
            trend_data=[],
        )
        mock_svc = MagicMock()
        mock_svc.build_noise_report.return_value = empty_report
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            resp = user_client.get("/reports/noise")
        html = resp.data.decode()
        # Should show summary cards with zero values, not empty state
        # (empty state only when report is None)
        assert "0.0%" in html

    def test_generic_exception_handled(self, user_client) -> None:
        mock_svc = MagicMock()
        mock_svc.build_noise_report.side_effect = RuntimeError("unexpected")
        with patch(REPORT_SVC_PATCH, return_value=mock_svc):
            resp = user_client.get("/reports/noise")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Unable to load noise report data" in html
        mock_svc.close.assert_called_once()
