"""Tests for Investigation routes."""

from unittest.mock import MagicMock, patch

import pytest
import respx
from flask.testing import FlaskClient
from httpx import Response


class TestFilterValidation:
    """Tests for filter validation functions."""

    def test_validate_status_valid(self) -> None:
        """Test valid status values pass validation."""
        from beeper_ui.routes.investigations import validate_status

        assert validate_status("investigating") == "investigating"
        assert validate_status("completed") == "completed"
        assert validate_status("failed") == "failed"
        assert validate_status("awaiting_confirmation") == "awaiting_confirmation"

    def test_validate_status_invalid(self) -> None:
        """Test invalid status values are rejected."""
        from beeper_ui.routes.investigations import validate_status

        assert validate_status("hacked") is None
        assert validate_status("") is None
        assert validate_status(None) is None

    def test_validate_severity_valid(self) -> None:
        """Test valid severity values pass validation."""
        from beeper_ui.routes.investigations import validate_severity

        assert validate_severity("low") == "low"
        assert validate_severity("critical") == "critical"

    def test_validate_severity_invalid(self) -> None:
        """Test invalid severity values are rejected."""
        from beeper_ui.routes.investigations import validate_severity

        assert validate_severity("extreme") is None
        assert validate_severity(None) is None

    def test_validate_service_valid(self) -> None:
        """Test valid service names pass validation."""
        from beeper_ui.routes.investigations import validate_service

        assert validate_service("payments") == "payments"
        assert validate_service("api-gateway") == "api-gateway"
        assert validate_service("my_service.v2") == "my_service.v2"

    def test_validate_service_invalid(self) -> None:
        """Test invalid service names are rejected."""
        from beeper_ui.routes.investigations import validate_service

        assert validate_service("../../etc/passwd") is None
        assert validate_service("service with spaces") is None
        assert validate_service("a" * 200) is None
        assert validate_service("") is None
        assert validate_service(None) is None

    def test_validate_date_range_valid(self) -> None:
        """Test valid date ranges pass validation."""
        from beeper_ui.routes.investigations import validate_date_range

        assert validate_date_range("today") == "today"
        assert validate_date_range("7d") == "7d"
        assert validate_date_range("30d") == "30d"
        assert validate_date_range("90d") == "90d"

    def test_validate_date_range_invalid(self) -> None:
        """Test invalid date ranges are rejected."""
        from beeper_ui.routes.investigations import validate_date_range

        assert validate_date_range("1y") is None
        assert validate_date_range("invalid") is None
        assert validate_date_range("") is None
        assert validate_date_range(None) is None


class TestDateRangeFiltering:
    """Tests for date range filtering logic."""

    def test_parse_date_range_today(self) -> None:
        """Test parsing 'today' date range."""
        from beeper_ui.routes.investigations import parse_date_range

        result = parse_date_range("today")
        assert result is not None
        assert result.hour == 0
        assert result.minute == 0

    def test_parse_date_range_none(self) -> None:
        """Test None input returns None."""
        from beeper_ui.routes.investigations import parse_date_range

        assert parse_date_range(None) is None
        assert parse_date_range("") is None

    def test_filter_by_date_range(self) -> None:
        """Test filtering investigations by date cutoff."""
        from datetime import datetime, timezone

        from beeper_ui.routes.investigations import filter_by_date_range
        from beeper_ui.services.investigation_service import Investigation

        recent = Investigation(
            id="inv-new", status="investigating", service="api",
            severity="high", condition="test",
            started_at="2026-03-06T12:00:00Z",
        )
        old = Investigation(
            id="inv-old", status="completed", service="api",
            severity="low", condition="old test",
            started_at="2020-01-01T00:00:00Z",
        )
        cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = filter_by_date_range([recent, old], cutoff)

        assert len(result) == 1
        assert result[0].id == "inv-new"

    def test_filter_by_date_range_uses_triggered_at_fallback(self) -> None:
        """Test date filtering falls back to triggered_at when no started_at."""
        from datetime import datetime, timezone

        from beeper_ui.routes.investigations import filter_by_date_range
        from beeper_ui.services.investigation_service import Investigation

        inv = Investigation(
            id="inv-1", status="investigating", service="api",
            severity="high", condition="test",
            started_at=None,
            triggered_at="2026-03-06T12:00:00Z",
        )
        cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = filter_by_date_range([inv], cutoff)
        assert len(result) == 1

    def test_filter_by_date_range_excludes_no_timestamp(self) -> None:
        """Test investigations without any timestamp are excluded."""
        from datetime import datetime, timezone

        from beeper_ui.routes.investigations import filter_by_date_range
        from beeper_ui.services.investigation_service import Investigation

        inv = Investigation(
            id="inv-1", status="investigating", service="api",
            severity="high", condition="test",
        )
        cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = filter_by_date_range([inv], cutoff)
        assert len(result) == 0


MOCK_INVESTIGATION_DETAIL = {
    "id": "inv-detail-001",
    "status": "investigating",
    "service": "payments",
    "severity": "high",
    "condition": "High error rate detected",
    "started_at": "2026-03-06T10:00:00Z",
    "completed_at": None,
    "triggered_at": "2026-03-06T09:55:00Z",
    "message": "Correlating signals across architectural layers",
    "error": None,
    "job_name": "inv-detail-001-job",
}


class TestInvestigationDetailRoute:
    """Tests for investigation detail route."""

    @respx.mock
    def test_detail_stream_content_type(self, client: FlaskClient) -> None:
        """Test detail SSE endpoint returns correct content type."""
        from beeper_ui.routes.investigations import investigation_detail_stream

        app = client.application
        with app.test_request_context("/investigations/inv-001/stream"):
            response = investigation_detail_stream("inv-001")
            assert "text/event-stream" in response.content_type
            assert response.headers.get("Cache-Control") == "no-cache"
            assert response.headers.get("Connection") == "keep-alive"
            response.close()

class TestStepStates:
    """Tests for step progress state calculation."""

    def test_step_states_all_completed(self) -> None:
        """Test all steps completed when phase is completed."""
        from beeper_ui.routes.investigations import _get_step_states

        states = _get_step_states(None, "completed")
        assert all(s["state"] == "completed" for s in states)
        assert len(states) == 6

    def test_step_states_active_step(self) -> None:
        """Test active step identified from message."""
        from beeper_ui.routes.investigations import _get_step_states

        states = _get_step_states(
            "Correlating signals across architectural layers", "investigating"
        )
        # Customer Impact and KB Query should be completed
        assert states[0]["state"] == "completed"
        assert states[1]["state"] == "completed"
        # Signal Correlation should be active
        assert states[2]["state"] == "active"
        assert states[2]["key"] == "signal_correlation"
        # Remaining should be pending
        assert states[3]["state"] == "pending"
        assert states[4]["state"] == "pending"
        assert states[5]["state"] == "pending"

    def test_step_states_first_step(self) -> None:
        """Test first step as active."""
        from beeper_ui.routes.investigations import _get_step_states

        states = _get_step_states("Assessing customer impact", "investigating")
        assert states[0]["state"] == "active"
        assert states[1]["state"] == "pending"

    def test_step_states_failed(self) -> None:
        """Test error state on failed investigation."""
        from beeper_ui.routes.investigations import _get_step_states

        states = _get_step_states(
            "Generating root cause hypothesis", "failed"
        )
        # Steps before RCA should be completed
        assert states[0]["state"] == "completed"
        assert states[1]["state"] == "completed"
        assert states[2]["state"] == "completed"
        # RCA step should be error
        assert states[3]["state"] == "error"
        assert states[3]["key"] == "rca_hypothesis"
        # After should be pending
        assert states[4]["state"] == "pending"
        assert states[5]["state"] == "pending"

    def test_step_states_no_message(self) -> None:
        """Test step states with no message returns all pending."""
        from beeper_ui.routes.investigations import _get_step_states

        states = _get_step_states(None, "investigating")
        assert all(s["state"] == "pending" for s in states)

    def test_step_states_last_step(self) -> None:
        """Test last step as active."""
        from beeper_ui.routes.investigations import _get_step_states

        states = _get_step_states("Documenting investigation findings", "investigating")
        assert states[0]["state"] == "completed"
        assert states[1]["state"] == "completed"
        assert states[2]["state"] == "completed"
        assert states[3]["state"] == "completed"
        assert states[4]["state"] == "completed"
        assert states[5]["state"] == "active"
        assert states[5]["key"] == "documentation"


class TestDetailSSEEventGeneration:
    """Tests for SSE event generation logic."""

    @pytest.fixture(autouse=True)
    def _mock_urgency_deps(self):
        with patch("beeper_ui.routes.investigations._get_slo_service") as mock_slo, \
             patch("beeper_ui.routes.investigations._get_urgency_service") as mock_urg:
            slo = MagicMock()
            slo.get_service_budget.return_value = None
            mock_slo.return_value = slo
            urg = MagicMock()
            urg.compute_batch_urgency.return_value = {}
            mock_urg.return_value = urg
            yield

    @respx.mock
    def test_sse_sends_step_update_on_message_change(
        self, client: FlaskClient
    ) -> None:
        """Test SSE sends step-update event when status.message changes."""
        from unittest.mock import patch

        detail_v1 = MOCK_INVESTIGATION_DETAIL.copy()
        detail_v1["message"] = "Assessing customer impact"

        detail_v2 = MOCK_INVESTIGATION_DETAIL.copy()
        detail_v2["message"] = "Querying knowledge base"

        # First call returns v1, second returns v2
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(
            side_effect=[
                Response(200, json=detail_v1),
                Response(200, json=detail_v2),
            ]
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ), patch(
            "beeper_ui.routes.investigations.time.sleep"
        ):
            from beeper_ui.routes.investigations import _generate_detail_sse_events

            app = client.application
            with app.app_context():
                gen = _generate_detail_sse_events(
                    "http://mock-operator:8080", 5.0, "inv-detail-001"
                )
                # First event: step-update with v1
                event1 = next(gen)
                assert "event: step-update" in event1

                # Second event: step-update with v2 (message changed)
                event2 = next(gen)
                assert "event: step-update" in event2

                gen.close()

    @respx.mock
    def test_sse_sends_complete_on_phase_completed(
        self, client: FlaskClient
    ) -> None:
        """Test SSE sends investigation-complete when phase is completed."""
        from unittest.mock import patch

        detail = MOCK_INVESTIGATION_DETAIL.copy()
        detail["status"] = "completed"

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=detail))

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ), patch(
            "beeper_ui.routes.investigations.time.sleep"
        ):
            from beeper_ui.routes.investigations import _generate_detail_sse_events

            app = client.application
            with app.app_context():
                gen = _generate_detail_sse_events(
                    "http://mock-operator:8080", 5.0, "inv-detail-001"
                )
                events = list(gen)
                # Should include a step-update and investigation-complete
                assert any("event: step-update" in e for e in events)
                assert any("event: investigation-complete" in e for e in events)
                assert any("data: done" in e for e in events)

    @respx.mock
    def test_sse_sends_not_found_event(self, client: FlaskClient) -> None:
        """Test SSE sends investigation-complete with not-found when 404."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-gone"
        ).mock(return_value=Response(404, json={"error": "not found"}))

        from beeper_ui.routes.investigations import _generate_detail_sse_events

        app = client.application
        with app.app_context():
            gen = _generate_detail_sse_events(
                "http://mock-operator:8080", 5.0, "inv-gone"
            )
            events = list(gen)
            assert len(events) == 1
            assert "event: investigation-complete" in events[0]
            assert "data: not-found" in events[0]

    @respx.mock
    def test_sse_sends_findings_update_on_new_data(
        self, client: FlaskClient
    ) -> None:
        """Test SSE sends findings-update when new findings appear."""
        from unittest.mock import patch

        detail = MOCK_INVESTIGATION_DETAIL.copy()

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=detail))

        findings_v1: dict[str, object] = {}
        findings_v2 = {
            "customer_impacting": True,
            "reasoning": "Users affected",
        }

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            side_effect=[findings_v1, findings_v2],
        ), patch(
            "beeper_ui.routes.investigations.time.sleep"
        ):
            from beeper_ui.routes.investigations import _generate_detail_sse_events

            app = client.application
            with app.app_context():
                gen = _generate_detail_sse_events(
                    "http://mock-operator:8080", 5.0, "inv-detail-001"
                )
                # First iteration: step-update (initial) + no findings
                event1 = next(gen)
                assert "event: step-update" in event1

                # Second iteration: no step change, but findings appeared
                event2 = next(gen)
                assert "event: findings-update" in event2

                gen.close()



MOCK_FINDINGS_WITH_RECOMMENDATIONS = {
    "customer_impacting": True,
    "reasoning": "Users experiencing payment failures",
    "root_cause_hypothesis": "Database pool exhausted",
    "confidence_percentage": 85,
    "confidence_level": "high",
    "recommendations": [
        {
            "action": "Scale database connection pool from 10 to 50",
            "confidence": "high",
            "expected_outcome": "Connection errors will stop within 2 minutes",
            "risk_assessment": "low",
            "based_on_prior_incident": "inc-2026-001",
        },
        {
            "action": "Restart the affected database pods",
            "confidence": "medium",
            "expected_outcome": "Clears stale connections and restores service",
            "risk_assessment": "medium",
            "based_on_prior_incident": None,
        },
        {
            "action": "Enable query timeout limits",
            "confidence": "low",
            "expected_outcome": "Prevents long-running queries from exhausting pool",
            "risk_assessment": "low",
            "based_on_prior_incident": None,
        },
    ],
    "recommendation_count": 3,
    "ranking_rationale": "Ranked by confidence level and risk assessment",
    "diagnostic_actions": [
        "Check database connection pool metrics",
        "Review slow query logs for the last hour",
    ],
    "synthesis_source": "llm",
    "resolution_model_tier": "standard",
    "resolution_model_used": "gpt-4",
    "alternative_hypotheses": [
        "Network partition between app and database",
        "Resource exhaustion on database host",
    ],
}


class TestRecommendationsDisplay:
    """Tests for recommendations and confidence display (Story 4-3)."""


    @respx.mock
    def test_sse_findings_update_includes_recommendations(
        self, client: FlaskClient
    ) -> None:
        """Test SSE findings-update event includes recommendation cards."""
        detail = MOCK_INVESTIGATION_DETAIL.copy()

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=detail))

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            side_effect=[{}, MOCK_FINDINGS_WITH_RECOMMENDATIONS],
        ), patch(
            "beeper_ui.routes.investigations.time.sleep"
        ):
            from beeper_ui.routes.investigations import _generate_detail_sse_events

            app = client.application
            with app.app_context():
                gen = _generate_detail_sse_events(
                    "http://mock-operator:8080", 5.0, "inv-detail-001"
                )
                # First: step-update (initial)
                event1 = next(gen)
                assert "event: step-update" in event1

                # Second: findings-update with recommendations
                event2 = next(gen)
                assert "event: findings-update" in event2
                assert "recommendation-card" in event2

                gen.close()



class TestRelatedKBNavigation:
    """Tests for KB entry navigation from investigations (Stories 4-4, 5-6)."""

    @respx.mock
    def test_related_kb_returns_semantically_ranked_entries(
        self, client: FlaskClient
    ) -> None:
        """Test related-kb route returns semantically ranked KB entries."""
        from beeper_ui.services.kb_surfacing_service import KBSurfacingResult

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        surfacing_result = KBSurfacingResult(
            entries=[
                {
                    "entry_id": "kb-001", "title": "Payments Runbook",
                    "entry_type": "proven_fix", "service": "payments",
                    "validation_status": "proven", "relevance_score": 0.8,
                    "composite_score": 2.4, "content_preview": "Some content",
                    "created_at": "2026-03-01", "link": "/knowledge/kb-001",
                },
                {
                    "entry_id": "kb-002", "title": "Payment Error Guide",
                    "entry_type": "investigation", "service": "payments",
                    "validation_status": "AI-generated",
                    "relevance_score": 0.9, "composite_score": 0.9,
                    "content_preview": "Other content",
                    "created_at": "2026-03-02", "link": "/knowledge/kb-002",
                },
            ],
            is_novel=False,
            query_text="test query",
            investigation_id="inv-detail-001",
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.surface_entries",
            return_value=surfacing_result,
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.close",
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.mark_novel_investigation",
        ):
            response = client.get("/investigations/inv-detail-001/related-kb")
            assert response.status_code == 200
            assert b"Payments Runbook" in response.data
            assert b"Payment Error Guide" in response.data
            assert b"Ranked by relevance" in response.data

    @respx.mock
    def test_related_kb_novel_issue_empty_state(self, client: FlaskClient) -> None:
        """Test related-kb renders novel issue banner when no entries found (AC #3)."""
        from beeper_ui.services.kb_surfacing_service import KBSurfacingResult

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        surfacing_result = KBSurfacingResult(
            entries=[],
            is_novel=True,
            query_text="unknown issue",
            investigation_id="inv-detail-001",
        )

        mock_mark = MagicMock()

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={"root_cause_hypothesis": "unknown"},
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.surface_entries",
            return_value=surfacing_result,
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.mark_novel_investigation",
            mock_mark,
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.close",
        ):
            response = client.get("/investigations/inv-detail-001/related-kb")
            assert response.status_code == 200
            assert b"No prior knowledge found" in response.data
            assert b"novel issue" in response.data
            assert b"kb-novel-issue" in response.data
            mock_mark.assert_called_once_with("inv-detail-001")

    @respx.mock
    def test_related_kb_exact_match_banner(self, client: FlaskClient) -> None:
        """Test prior research banner appears with exact match."""
        from beeper_ui.services.kb_surfacing_service import KBSurfacingResult

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        exact_entry = _make_mock_kb_entry(
            "kb-exact-001", "Exact Prior Incident", "payments"
        )

        surfacing_result = KBSurfacingResult(
            entries=[], is_novel=False,
            query_text="test", investigation_id="inv-detail-001",
        )

        mock_kb_svc = MagicMock()
        mock_kb_svc.get_entry.return_value = exact_entry

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={
                "exact_match_found": True,
                "exact_match_id": "kb-exact-001",
            },
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.surface_entries",
            return_value=surfacing_result,
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.kb_service",
            new_callable=lambda: property(lambda self: mock_kb_svc),
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.close",
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.mark_novel_investigation",
        ):
            response = client.get("/investigations/inv-detail-001/related-kb")
            assert response.status_code == 200
            # Task 4.4: prior-research banner migrated into the Tailwind
            # kb_panel (no legacy .prior-research-banner class).
            assert b"Building on prior research" in response.data
            assert b"Exact Prior Incident" in response.data

    @respx.mock
    def test_related_kb_operator_failure_returns_empty(
        self, client: FlaskClient
    ) -> None:
        """Test related-kb handles operator failure gracefully."""
        import httpx

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(side_effect=httpx.ConnectError("Connection refused"))

        response = client.get("/investigations/inv-detail-001/related-kb")
        assert response.status_code == 200
        assert b"No related KB entries found" in response.data

    @respx.mock
    def test_related_kb_feedback_buttons_present(self, client: FlaskClient) -> None:
        """Test feedback buttons render for each surfaced entry (AC #2)."""
        from beeper_ui.services.kb_surfacing_service import KBSurfacingResult

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        surfacing_result = KBSurfacingResult(
            entries=[
                {"entry_id": "kb-fb-001", "title": "Test Entry", "entry_type": "investigation",
                 "service": "payments", "validation_status": "AI-generated", "relevance_score": 0.8,
                 "composite_score": 0.8, "content_preview": "Content", "created_at": "2026-03-01",
                 "link": "/knowledge/kb-fb-001"},
            ],
            is_novel=False,
            query_text="test",
            investigation_id="inv-detail-001",
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.surface_entries",
            return_value=surfacing_result,
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.close",
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.mark_novel_investigation",
        ):
            response = client.get("/investigations/inv-detail-001/related-kb")
            assert response.status_code == 200
            assert b"kb-feedback-relevant" in response.data
            assert b"kb-feedback-not-relevant" in response.data
            assert b'data-entry-id="kb-fb-001"' in response.data

    @respx.mock
    def test_related_kb_validation_ranking_display(self, client: FlaskClient) -> None:
        """Test validation status badges show correct indicators (AC #1)."""
        from beeper_ui.services.kb_surfacing_service import KBSurfacingResult

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        surfacing_result = KBSurfacingResult(
            entries=[
                {
                    "entry_id": "kb-proven", "title": "Proven Fix",
                    "entry_type": "proven_fix", "service": "payments",
                    "validation_status": "proven", "relevance_score": 0.6,
                    "composite_score": 1.8,
                    "content_preview": "Proven content",
                    "created_at": "2026-03-01",
                    "link": "/knowledge/kb-proven",
                },
                {
                    "entry_id": "kb-ai", "title": "AI Entry",
                    "entry_type": "investigation", "service": "payments",
                    "validation_status": "AI-generated",
                    "relevance_score": 0.9, "composite_score": 0.9,
                    "content_preview": "AI content",
                    "created_at": "2026-03-02",
                    "link": "/knowledge/kb-ai",
                },
            ],
            is_novel=False,
            query_text="test",
            investigation_id="inv-detail-001",
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.surface_entries",
            return_value=surfacing_result,
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.close",
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.mark_novel_investigation",
        ):
            response = client.get("/investigations/inv-detail-001/related-kb")
            assert response.status_code == 200
            # Task 4.4: validation status surfaced as Tailwind chips with the
            # status text (no legacy .validation-proven class names).
            assert b"proven" in response.data
            assert b"AI-generated" in response.data
            # Proven entry appears first (higher composite score)
            proven_pos = response.data.find(b"Proven Fix")
            ai_pos = response.data.find(b"AI Entry")
            assert proven_pos < ai_pos


    @respx.mock
    def test_kb_entry_links_open_new_tab(
        self, client: FlaskClient
    ) -> None:
        """Test KB entry links have target=_blank for new tab."""
        from beeper_ui.services.kb_surfacing_service import KBSurfacingResult

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        surfacing_result = KBSurfacingResult(
            entries=[
                {
                    "entry_id": "kb-001", "title": "Test Entry",
                    "entry_type": "investigation", "service": "payments",
                    "validation_status": "AI-generated",
                    "relevance_score": 0.8, "composite_score": 0.8,
                    "content_preview": "Test content",
                    "created_at": "2026-03-01",
                    "link": "/knowledge/kb-001",
                },
            ],
            is_novel=False,
            query_text="test",
            investigation_id="inv-detail-001",
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.surface_entries",
            return_value=surfacing_result,
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.close",
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.mark_novel_investigation",
        ):
            response = client.get("/investigations/inv-detail-001/related-kb")
            assert response.status_code == 200
            assert b'target="_blank"' in response.data


    @respx.mock
    def test_related_kb_not_found_investigation(
        self, client: FlaskClient
    ) -> None:
        """Test related-kb returns empty when investigation not found."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-nonexistent"
        ).mock(return_value=Response(404, json={"error": "not found"}))

        response = client.get("/investigations/inv-nonexistent/related-kb")
        assert response.status_code == 200
        assert b"No related KB entries found" in response.data


    @respx.mock
    def test_sse_kb_update_event_renders_related_kb(
        self, client: FlaskClient
    ) -> None:
        """Test SSE sends kb-update event when prior_research_summary appears."""
        from unittest.mock import patch

        detail = MOCK_INVESTIGATION_DETAIL.copy()

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=detail))

        findings_v1: dict[str, object] = {}
        findings_v2: dict[str, object] = {
            "customer_impacting": True,
            "reasoning": "Users affected",
            "prior_research_summary": "Found matching KB entry",
            "exact_match_found": True,
            "exact_match_id": "kb-match-sse",
        }

        from beeper_ui.services.kb_surfacing_service import KBSurfacingResult

        surfacing_result = KBSurfacingResult(
            entries=[
                {
                    "entry_id": "kb-001", "title": "SSE KB Entry",
                    "entry_type": "investigation",
                    "service": "payments",
                    "validation_status": "AI-generated",
                    "relevance_score": 0.8, "composite_score": 0.8,
                    "content_preview": "Test",
                    "created_at": "2026-03-01",
                    "link": "/knowledge/kb-001",
                },
            ],
            is_novel=False,
            query_text="test",
            investigation_id="inv-detail-001",
        )
        exact_entry = _make_mock_kb_entry(
            "kb-match-sse", "Exact SSE Match", "payments"
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            side_effect=[findings_v1, findings_v2],
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.surface_entries",
            return_value=surfacing_result,
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.close",
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.mark_novel_investigation",
        ), patch(
            "beeper_ui.services.kb_service.KBService.get_entry",
            return_value=exact_entry,
        ), patch(
            "beeper_ui.routes.investigations.time.sleep"
        ):
            from beeper_ui.routes.investigations import (
                _generate_detail_sse_events,
            )

            app = client.application
            with app.app_context():
                gen = _generate_detail_sse_events(
                    "http://mock-operator:8080", 5.0, "inv-detail-001"
                )
                # First iteration: step-update (initial) + no findings
                event1 = next(gen)
                assert "event: step-update" in event1

                # Second iteration: findings appeared with prior_research_summary
                # Should get findings, evidence, timeline, AND kb-update
                events = []
                event2 = next(gen)
                events.append(event2)
                event3 = next(gen)
                events.append(event3)
                event4 = next(gen)
                events.append(event4)
                event5 = next(gen)
                events.append(event5)

                all_events = "\n".join(events)
                assert "event: findings-update" in all_events
                assert "event: kb-update" in all_events

                gen.close()

    @respx.mock
    def test_sse_kb_update_sent_only_once(
        self, client: FlaskClient
    ) -> None:
        """Test SSE kb-update event is only sent once per stream.

        Iteration 1: findings with prior_research_summary → yields
            step-update, findings-update, evidence-update, timeline-update,
            kb-update (5 events)
        Iteration 2: findings with additional key → yields
            findings-update, evidence-update, timeline-update (3 events,
            NO second kb-update, NO remediation-update since no remediation keys)
        """
        from unittest.mock import patch

        detail = MOCK_INVESTIGATION_DETAIL.copy()

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=detail))

        findings_with_kb: dict[str, object] = {
            "prior_research_summary": "Found matching KB entry",
            "exact_match_found": False,
        }
        findings_with_kb_v2: dict[str, object] = {
            "prior_research_summary": "Found matching KB entry",
            "exact_match_found": False,
            "new_key": "new data",
        }

        from beeper_ui.services.kb_surfacing_service import KBSurfacingResult

        surfacing_result = KBSurfacingResult(
            entries=[],
            is_novel=True,
            query_text="test",
            investigation_id="inv-detail-001",
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            side_effect=[findings_with_kb, findings_with_kb_v2],
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.surface_entries",
            return_value=surfacing_result,
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.close",
        ), patch(
            "beeper_ui.routes.investigations.KBSurfacingService.mark_novel_investigation",
        ), patch(
            "beeper_ui.routes.investigations.time.sleep"
        ):
            from beeper_ui.routes.investigations import (
                _generate_detail_sse_events,
            )

            app = client.application
            with app.app_context():
                gen = _generate_detail_sse_events(
                    "http://mock-operator:8080", 5.0, "inv-detail-001"
                )
                # Iteration 1: step, findings, evidence, timeline, kb (5)
                # Iteration 2: findings, evidence, timeline (3)
                # No remediation-update (findings lack remediation keys, stage stays None)
                # Total: 8 events
                all_events_text = ""
                for _ in range(8):
                    event = next(gen)
                    all_events_text += event

                # kb-update should appear exactly once (from iteration 1 only)
                assert all_events_text.count("event: kb-update") == 1
                # findings-update should appear twice (once per iteration)
                assert all_events_text.count("event: findings-update") == 2
                # remediation-update should not appear (no remediation keys in findings)
                assert all_events_text.count("event: remediation-update") == 0

                gen.close()


MOCK_COMPLETED_DETAIL = {
    "id": "inv-completed-001",
    "status": "completed",
    "service": "payments",
    "severity": "high",
    "condition": "High error rate detected",
    "started_at": "2026-03-06T10:00:00Z",
    "completed_at": "2026-03-06T10:30:00Z",
    "triggered_at": "2026-03-06T09:55:00Z",
    "message": "Investigation complete",
    "error": None,
    "job_name": "inv-completed-001-job",
}


class TestResolutionConfirmation:
    """Tests for resolution confirmation workflow (Story 4-5)."""

    @respx.mock
    def test_confirm_resolution_success(self, client: FlaskClient) -> None:
        """Test POST confirm returns success result."""
        respx.post(
            "http://mock-operator:8080/api/v1/investigations/inv-completed-001/confirm"
        ).mock(
            return_value=Response(
                200, json={"status": "ok", "message": "Resolution confirmed"}
            )
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.save_resolution_feedback"
        ) as mock_save:
            response = client.post(
                "/investigations/inv-completed-001/confirm",
                data={"comment": "Confirmed by SRE"},
            )
            assert response.status_code == 200
            assert b"Resolution Confirmed" in response.data
            assert b"confirmation-success" in response.data
            assert b"Confirmed by SRE" in response.data
            # Verify feedback saved
            mock_save.assert_called_once()
            call_args = mock_save.call_args
            assert call_args[0][0] == "inv-completed-001"
            assert call_args[0][1]["resolution_action"] == "confirmed"
            assert call_args[0][1]["resolution_comment"] == "Confirmed by SRE"

    @respx.mock
    def test_confirm_resolution_no_comment(self, client: FlaskClient) -> None:
        """Test confirm works without optional comment."""
        respx.post(
            "http://mock-operator:8080/api/v1/investigations/inv-completed-001/confirm"
        ).mock(
            return_value=Response(
                200, json={"status": "ok", "message": "Resolution confirmed"}
            )
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.save_resolution_feedback"
        ):
            response = client.post(
                "/investigations/inv-completed-001/confirm",
                data={},
            )
            assert response.status_code == 200
            assert b"Resolution Confirmed" in response.data

    @respx.mock
    def test_confirm_resolution_not_found(self, client: FlaskClient) -> None:
        """Test confirm returns 404 when investigation not found."""
        respx.post(
            "http://mock-operator:8080/api/v1/investigations/inv-gone/confirm"
        ).mock(return_value=Response(404, json={"error": "not found"}))

        response = client.post("/investigations/inv-gone/confirm", data={})
        assert response.status_code == 404
        assert b"Investigation not found" in response.data

    @respx.mock
    def test_confirm_resolution_operator_error(self, client: FlaskClient) -> None:
        """Test confirm returns 503 when operator unavailable."""
        import httpx

        respx.post(
            "http://mock-operator:8080/api/v1/investigations/inv-001/confirm"
        ).mock(side_effect=httpx.ConnectError("Connection refused"))

        response = client.post("/investigations/inv-001/confirm", data={})
        assert response.status_code == 503
        assert b"Unable to connect" in response.data

    @respx.mock
    def test_reject_resolution_success(self, client: FlaskClient) -> None:
        """Test POST reject returns success result with reason."""
        respx.post(
            "http://mock-operator:8080/api/v1/investigations/inv-completed-001/reject"
        ).mock(
            return_value=Response(
                200, json={"status": "ok", "message": "Resolution rejected"}
            )
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.save_resolution_feedback"
        ) as mock_save:
            response = client.post(
                "/investigations/inv-completed-001/reject",
                data={
                    "rejection_reason": "hypothesis_incorrect",
                    "reason_details": "Root cause is network, not DB",
                    "correction": "Check network connectivity",
                },
            )
            assert response.status_code == 200
            assert b"Resolution Rejected" in response.data
            assert b"confirmation-rejected" in response.data
            assert b"Hypothesis incorrect" in response.data
            assert b"Root cause is network, not DB" in response.data
            assert b"Check network connectivity" in response.data
            # Verify feedback saved
            mock_save.assert_called_once()
            call_args = mock_save.call_args
            assert call_args[0][1]["resolution_action"] == "rejected"
            assert call_args[0][1]["rejection_reason"] == "hypothesis_incorrect"

    @respx.mock
    def test_reject_resolution_not_found(self, client: FlaskClient) -> None:
        """Test reject returns 404 when investigation not found."""
        respx.post(
            "http://mock-operator:8080/api/v1/investigations/inv-gone/reject"
        ).mock(return_value=Response(404, json={"error": "not found"}))

        response = client.post(
            "/investigations/inv-gone/reject",
            data={
                "rejection_reason": "other",
                "reason_details": "Test rejection",
            },
        )
        assert response.status_code == 404
        assert b"Investigation not found" in response.data

    def test_reject_invalid_reason(self, client: FlaskClient) -> None:
        """Test reject returns 400 for invalid rejection reason."""
        response = client.post(
            "/investigations/inv-001/reject",
            data={
                "rejection_reason": "invalid_reason",
                "reason_details": "Test",
            },
        )
        assert response.status_code == 400
        assert b"Invalid rejection reason" in response.data

    def test_reject_missing_details(self, client: FlaskClient) -> None:
        """Test reject returns 400 when reason_details is missing."""
        response = client.post(
            "/investigations/inv-001/reject",
            data={
                "rejection_reason": "hypothesis_incorrect",
                "reason_details": "",
            },
        )
        assert response.status_code == 400
        assert b"provide details" in response.data

    def test_reject_missing_reason(self, client: FlaskClient) -> None:
        """Test reject returns 400 when rejection_reason is empty."""
        response = client.post(
            "/investigations/inv-001/reject",
            data={
                "rejection_reason": "",
                "reason_details": "Some details",
            },
        )
        assert response.status_code == 400
        assert b"Invalid rejection reason" in response.data

    @respx.mock
    def test_reject_operator_error(self, client: FlaskClient) -> None:
        """Test reject returns 503 when operator unavailable."""
        import httpx

        respx.post(
            "http://mock-operator:8080/api/v1/investigations/inv-001/reject"
        ).mock(side_effect=httpx.ConnectError("Connection refused"))

        response = client.post(
            "/investigations/inv-001/reject",
            data={
                "rejection_reason": "other",
                "reason_details": "Test",
            },
        )
        assert response.status_code == 503
        assert b"Unable to connect" in response.data


    @respx.mock
    def test_sse_confirmation_update_independent_of_key_changes(
        self, client: FlaskClient
    ) -> None:
        """Test SSE confirmation-update fires even when findings keys don't change.

        When resolution_action value changes but no new keys are added,
        the confirmation-update event should still fire.
        """
        detail = MOCK_COMPLETED_DETAIL.copy()
        detail["status"] = "awaiting_confirmation"
        detail["id"] = "inv-awaiting-002"

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-awaiting-002"
        ).mock(return_value=Response(200, json=detail))

        # Same keys, but resolution_action value changes
        findings_v1: dict[str, object] = {
            "customer_impacting": True,
            "recommendations": [{"action": "test", "confidence": "high"}],
            "resolution_action": "rejected",
            "rejection_reason": "hypothesis_incorrect",
        }
        findings_v2: dict[str, object] = {
            "customer_impacting": True,
            "recommendations": [{"action": "test", "confidence": "high"}],
            "resolution_action": "confirmed",
            "rejection_reason": "hypothesis_incorrect",
        }

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            side_effect=[findings_v1, findings_v2],
        ), patch(
            "beeper_ui.routes.investigations.time.sleep"
        ):
            from beeper_ui.routes.investigations import (
                _generate_detail_sse_events,
            )

            app = client.application
            with app.app_context():
                gen = _generate_detail_sse_events(
                    "http://mock-operator:8080", 5.0, "inv-awaiting-002"
                )
                # Iteration 1: step-update, findings-update, evidence-update,
                # evidence-timeline-update, confirmation-update
                # (no remediation-update: findings lack remediation keys)
                # Iteration 2: no key change, but resolution_action changed → confirmation-update
                events = []
                for _ in range(6):
                    events.append(next(gen))

                all_text = "\n".join(events)
                # confirmation-update should fire twice (once per value change)
                assert all_text.count("event: confirmation-update") == 2

                gen.close()

    @respx.mock
    def test_sse_confirmation_update_event(
        self, client: FlaskClient
    ) -> None:
        """Test SSE sends confirmation-update event when resolution_action changes."""
        # Use awaiting_confirmation so the generator doesn't exit on first iteration
        detail = MOCK_COMPLETED_DETAIL.copy()
        detail["status"] = "awaiting_confirmation"
        detail["id"] = "inv-awaiting-001"

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-awaiting-001"
        ).mock(return_value=Response(200, json=detail))

        findings_v1: dict[str, object] = {
            "customer_impacting": True,
            "recommendations": [{"action": "test", "confidence": "high"}],
        }
        findings_v2 = dict(findings_v1)
        findings_v2["resolution_action"] = "confirmed"
        findings_v2["new_key"] = "trigger_update"

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            side_effect=[findings_v1, findings_v2, findings_v2],
        ), patch(
            "beeper_ui.routes.investigations.time.sleep"
        ):
            from beeper_ui.routes.investigations import (
                _generate_detail_sse_events,
            )

            app = client.application
            with app.app_context():
                gen = _generate_detail_sse_events(
                    "http://mock-operator:8080", 5.0, "inv-awaiting-001"
                )
                # Iteration 1 yields: step-update, findings-update, evidence-update,
                # evidence-timeline-update
                # Iteration 2 yields: findings-update, evidence-update, evidence-timeline-update,
                # confirmation-update
                # (no remediation-update: findings lack remediation keys)
                # Total: 8 events
                events = []
                for _ in range(8):
                    events.append(next(gen))

                all_text = "\n".join(events)
                assert "event: step-update" in all_text
                assert "event: findings-update" in all_text
                # confirmation-update fires when resolution_action changes from None to "confirmed"
                assert "event: confirmation-update" in all_text

                gen.close()


def _make_mock_kb_entry(
    entry_id: str, title: str, service: str
) -> object:
    """Create a mock KBEntry-like object for testing."""
    from unittest.mock import MagicMock

    entry = MagicMock()
    entry.id = entry_id
    entry.entry_id = entry_id
    entry.title = title
    entry.service = service
    entry.entry_type = "investigation"
    entry.content = "Sample content for testing purposes."
    entry.created_at = None
    entry.updated_at = None
    entry.author = "beeper"
    entry.version = 1
    entry.tags = []
    entry.relevance_score = None
    return entry


class TestInvestigationResolution:
    """Tests for investigation resolution workflow (Story 4-6)."""

    @respx.mock
    def test_resolve_resolved_success(self, client: FlaskClient) -> None:
        """Test POST resolve with outcome=resolved returns success."""
        # Mock the get_investigation call (for MTTR calculation)
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-001"
        ).mock(
            return_value=Response(200, json={
                "id": "inv-001", "status": "completed", "service": "payments",
                "severity": "high", "condition": "Error rate", "started_at": "2026-03-07T10:00:00Z",
            })
        )
        respx.post(
            "http://mock-operator:8080/api/v1/investigations/inv-001/resolve"
        ).mock(
            return_value=Response(200, json={"status": "resolved", "message": "OK"})
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.save_resolution_feedback"
        ) as mock_save, patch(
            "beeper_ui.routes.investigations.InvestigationService.update_kb_with_resolution",
            return_value=True,
        ):
            response = client.post(
                "/investigations/inv-001/resolve",
                data={
                    "outcome": "resolved",
                    "accuracy_rating": "correct",
                    "resolution_notes": "Restarted service",
                },
            )
            assert response.status_code == 200
            assert b"Investigation Resolved" in response.data
            assert b"resolution-resolved" in response.data
            assert b"Correct" in response.data
            # Verify feedback saved with MTTR
            mock_save.assert_called_once()
            feedback = mock_save.call_args[0][1]
            assert feedback["resolution_outcome"] == "resolved"
            assert feedback["accuracy_rating"] == "correct"
            assert feedback["mttr_seconds"] is not None

    @respx.mock
    def test_resolve_not_an_issue(self, client: FlaskClient) -> None:
        """Test resolve with outcome=not_an_issue."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-001"
        ).mock(
            return_value=Response(200, json={
                "id": "inv-001", "status": "completed", "service": "payments",
                "severity": "low", "condition": "Alert", "started_at": "2026-03-07T10:00:00Z",
            })
        )
        respx.post(
            "http://mock-operator:8080/api/v1/investigations/inv-001/resolve"
        ).mock(
            return_value=Response(200, json={"status": "not_an_issue", "message": "OK"})
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.save_resolution_feedback"
        ), patch(
            "beeper_ui.routes.investigations.InvestigationService.update_kb_with_resolution",
            return_value=False,
        ):
            response = client.post(
                "/investigations/inv-001/resolve",
                data={
                    "outcome": "not_an_issue",
                    "not_an_issue_reason": "false_positive",
                },
            )
            assert response.status_code == 200
            assert b"Not an Issue" in response.data
            assert b"resolution-not-an-issue" in response.data

    @respx.mock
    def test_resolve_escalated(self, client: FlaskClient) -> None:
        """Test resolve with outcome=escalated."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-001"
        ).mock(
            return_value=Response(200, json={
                "id": "inv-001", "status": "awaiting_confirmation", "service": "payments",
                "severity": "high", "condition": "Error", "started_at": "2026-03-07T10:00:00Z",
            })
        )
        respx.post(
            "http://mock-operator:8080/api/v1/investigations/inv-001/resolve"
        ).mock(
            return_value=Response(200, json={"status": "escalated", "message": "OK"})
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.save_resolution_feedback"
        ) as mock_save:
            response = client.post(
                "/investigations/inv-001/resolve",
                data={
                    "outcome": "escalated",
                    "escalation_target": "platform-team",
                    "resolution_notes": "Needs platform team",
                },
            )
            assert response.status_code == 200
            assert b"Escalated" in response.data
            assert b"platform-team" in response.data
            assert b"resolution-escalated" in response.data
            # MTTR should not be calculated for escalated
            feedback = mock_save.call_args[0][1]
            assert feedback["mttr_seconds"] is None

    @respx.mock
    def test_resolve_unresolved(self, client: FlaskClient) -> None:
        """Test resolve with outcome=unresolved."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-001"
        ).mock(
            return_value=Response(200, json={
                "id": "inv-001", "status": "completed", "service": "payments",
                "severity": "medium", "condition": "Spike", "started_at": "2026-03-07T10:00:00Z",
            })
        )
        respx.post(
            "http://mock-operator:8080/api/v1/investigations/inv-001/resolve"
        ).mock(
            return_value=Response(200, json={"status": "unresolved", "message": "OK"})
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.save_resolution_feedback"
        ), patch(
            "beeper_ui.routes.investigations.InvestigationService.update_kb_with_resolution",
            return_value=True,
        ):
            response = client.post(
                "/investigations/inv-001/resolve",
                data={"outcome": "unresolved", "resolution_notes": "Cannot determine root cause"},
            )
            assert response.status_code == 200
            assert b"Unresolved" in response.data
            assert b"resolution-unresolved" in response.data

    def test_resolve_invalid_outcome(self, client: FlaskClient) -> None:
        """Test resolve with invalid outcome returns 400."""
        response = client.post(
            "/investigations/inv-001/resolve",
            data={"outcome": "invalid_outcome"},
        )
        assert response.status_code == 400
        assert b"Invalid resolution outcome" in response.data

    def test_resolve_invalid_accuracy(self, client: FlaskClient) -> None:
        """Test resolve with invalid accuracy rating returns 400."""
        response = client.post(
            "/investigations/inv-001/resolve",
            data={"outcome": "resolved", "accuracy_rating": "wrong_value"},
        )
        assert response.status_code == 400
        assert b"Invalid accuracy rating" in response.data

    def test_resolve_invalid_not_an_issue_reason(self, client: FlaskClient) -> None:
        """Test resolve with invalid not_an_issue_reason returns 400."""
        response = client.post(
            "/investigations/inv-001/resolve",
            data={"outcome": "not_an_issue", "not_an_issue_reason": "invalid_reason"},
        )
        assert response.status_code == 400
        assert b"Invalid reason" in response.data

    def test_resolve_escalated_no_target(self, client: FlaskClient) -> None:
        """Test escalated without target returns 400."""
        response = client.post(
            "/investigations/inv-001/resolve",
            data={"outcome": "escalated"},
        )
        assert response.status_code == 400
        assert b"escalation target" in response.data

    @respx.mock
    def test_resolve_operator_error(self, client: FlaskClient) -> None:
        """Test resolve returns 503 when operator unavailable."""
        import httpx

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-001"
        ).mock(side_effect=httpx.ConnectError("Connection refused"))

        response = client.post(
            "/investigations/inv-001/resolve",
            data={"outcome": "resolved"},
        )
        assert response.status_code == 503
        assert b"Unable to connect" in response.data

    @respx.mock
    def test_resolve_not_found(self, client: FlaskClient) -> None:
        """Test resolve returns 404 when investigation not found."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-gone"
        ).mock(
            return_value=Response(200, json={
                "id": "inv-gone", "status": "completed", "service": "test",
                "severity": "low", "condition": "Test",
            })
        )
        respx.post(
            "http://mock-operator:8080/api/v1/investigations/inv-gone/resolve"
        ).mock(return_value=Response(404, json={"error": "not found"}))

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.save_resolution_feedback"
        ):
            response = client.post(
                "/investigations/inv-gone/resolve",
                data={"outcome": "resolved"},
            )
            assert response.status_code == 404
            assert b"Investigation not found" in response.data


    @respx.mock
    def test_sse_resolution_update_event(self, client: FlaskClient) -> None:
        """Test SSE fires resolution-update when resolution_outcome appears."""
        from beeper_ui.routes.investigations import _generate_detail_sse_events

        # First poll: awaiting_confirmation, no resolution_outcome
        findings_before: dict[str, object] = {"recommendations": [{"action": "restart"}]}
        # Second poll: completed with resolution_outcome
        findings_after: dict[str, object] = {
            "recommendations": [{"action": "restart"}],
            "resolution_outcome": "resolved",
            "accuracy_rating": "correct",
        }

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-001"
        ).mock(
            side_effect=[
                Response(200, json={
                    "id": "inv-001", "status": "awaiting_confirmation",
                    "service": "test", "severity": "low", "condition": "Test",
                    "started_at": "2026-03-07T10:00:00Z",
                }),
                Response(200, json={
                    "id": "inv-001", "status": "completed", "service": "test",
                    "severity": "low", "condition": "Test",
                    "started_at": "2026-03-07T10:00:00Z",
                }),
            ]
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            side_effect=[findings_before, findings_after],
        ), patch(
            "beeper_ui.routes.investigations.time.sleep"
        ):
            app = client.application
            with app.app_context():
                gen = _generate_detail_sse_events(
                    "http://mock-operator:8080", 5.0, "inv-001"
                )
                events: list[str] = []
                try:
                    for _ in range(20):
                        event = next(gen)
                        events.append(event)
                        if "investigation-complete" in event:
                            break
                except StopIteration:
                    pass
                gen.close()

                all_events = "".join(events)
                assert "resolution-update" in all_events


    @respx.mock
    def test_sse_resolution_update_independent_of_key_changes(
        self, client: FlaskClient
    ) -> None:
        """Test SSE resolution-update fires on value-only change without key change.

        When resolution_outcome value changes but no new keys are added,
        the resolution-update event should still fire.
        """
        detail = {
            "id": "inv-res-002", "status": "awaiting_confirmation",
            "service": "test", "severity": "low", "condition": "Test",
            "started_at": "2026-03-07T10:00:00Z",
        }

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-res-002"
        ).mock(return_value=Response(200, json=detail))

        # Same keys, but resolution_outcome value changes
        findings_v1: dict[str, object] = {
            "customer_impacting": True,
            "recommendations": [{"action": "test", "confidence": "high"}],
            "resolution_outcome": "escalated",
        }
        findings_v2: dict[str, object] = {
            "customer_impacting": True,
            "recommendations": [{"action": "test", "confidence": "high"}],
            "resolution_outcome": "resolved",
        }

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            side_effect=[findings_v1, findings_v2],
        ), patch(
            "beeper_ui.routes.investigations.time.sleep"
        ):
            from beeper_ui.routes.investigations import (
                _generate_detail_sse_events,
            )

            app = client.application
            with app.app_context():
                gen = _generate_detail_sse_events(
                    "http://mock-operator:8080", 5.0, "inv-res-002"
                )
                # Iteration 1: step-update, findings-update, evidence-update,
                # evidence-timeline-update, resolution-update (5)
                # (no remediation-update: findings lack remediation keys)
                # Iteration 2: resolution-update only (value changed, no key change) (1)
                events = []
                for _ in range(6):
                    events.append(next(gen))

                all_text = "\n".join(events)
                # resolution-update should fire twice (once per value change)
                assert all_text.count("event: resolution-update") == 2

                gen.close()


class TestFormatMTTR:
    """Tests for format_mttr() helper."""

    def test_format_mttr_none(self) -> None:
        """Test None returns N/A."""
        from beeper_ui.routes.investigations import format_mttr

        assert format_mttr(None) == "N/A"

    def test_format_mttr_sub_minute(self) -> None:
        """Test <60 seconds returns <1m."""
        from beeper_ui.routes.investigations import format_mttr

        assert format_mttr(30) == "<1m"
        assert format_mttr(0) == "<1m"

    def test_format_mttr_minutes(self) -> None:
        """Test minutes formatting."""
        from beeper_ui.routes.investigations import format_mttr

        assert format_mttr(300) == "5m"
        assert format_mttr(3420) == "57m"

    def test_format_mttr_hours(self) -> None:
        """Test hours formatting."""
        from beeper_ui.routes.investigations import format_mttr

        assert format_mttr(3600) == "1h"
        assert format_mttr(7500) == "2h 5m"

    def test_format_mttr_days(self) -> None:
        """Test days formatting."""
        from beeper_ui.routes.investigations import format_mttr

        assert format_mttr(86400) == "1d"
        assert format_mttr(97200) == "1d 3h"


