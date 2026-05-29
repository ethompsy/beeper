"""Task 5.1 — Knowledge Base browsing, search & detail views.

One test per acceptance criterion (FR28/FR29/FR31 + empty state). Each proves
the criterion via Flask test-client render assertions (and static-source
assertions where the contract lives in shipped templates), per the repo's
no-JS-runner convention.

    AC1 (FR28): Learn > KB lists entries with service / title / date.
    AC2 (FR29): Search by keyword or service filters to matches.
    AC3 (FR31): Entry detail shows root cause, resolution, affected services,
                source investigation ref.
    AC4:        Empty KB renders an explanatory empty state, not blank.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask
from flask.testing import FlaskClient

from beeper_ui.services.embedding_service import EmbeddingService
from beeper_ui.services.kb_service import KBEntry

TEMPLATES = Path(__file__).resolve().parents[1] / "beeper_ui" / "templates" / "knowledge"


def _make_entry(
    entry_id: str = "kb-123",
    entry_type: str = "investigation",
    title: str = "Test Entry",
    content: str = "Test content",
    service: str = "api",
    created_at: datetime | None = None,
    root_cause: str | None = None,
    resolution: str | None = None,
    affected_services: list[str] | None = None,
) -> KBEntry:
    """Build a KBEntry for rendering tests."""
    return KBEntry(
        id="point-1",
        entry_id=entry_id,
        entry_type=entry_type,
        title=title,
        content=content,
        service=service,
        created_at=created_at,
        updated_at=None,
        author="beeper",
        version=1,
        tags=["test"],
        root_cause=root_cause,
        resolution=resolution,
        affected_services=affected_services or [],
    )


class TestAC1ListShowsServiceTitleDate:
    """AC1 / FR28: KB index lists entries with service, title and date."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_index_lists_service_title_and_date(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        created = datetime(2026, 5, 1, 14, 30, tzinfo=timezone.utc)
        mock_service.list_recent_entries.return_value = [
            _make_entry(
                "kb-1",
                "investigation",
                "Payment latency spike",
                service="payments",
                created_at=created,
            ),
        ]
        mock_service.get_available_services.return_value = ["payments"]
        mock_service.get_entry_types.return_value = ["investigation"]

        response = client.get("/knowledge/")
        body = response.data.decode()

        assert response.status_code == 200
        # title
        assert "Payment latency spike" in body
        # service
        assert "payments" in body
        # date (rendered as %Y-%m-%d %H:%M in the entry card)
        assert "2026-05-01 14:30" in body

    def test_entry_card_uses_dark_tokens_not_legacy_only(self, app: Flask) -> None:
        """Migrated card is Tailwind dark-token only — the structural fields and
        the type badge render through the shared component."""
        created = datetime(2026, 5, 1, 14, 30, tzinfo=timezone.utc)
        with app.app_context():
            html = app.jinja_env.get_template("knowledge/_entry_card.html").render(
                entry=_make_entry(
                    "kb-1", "runbook", "Restart API", service="api", created_at=created
                )
            )
        # FR28 fields present
        assert "Restart API" in html
        assert "api" in html
        assert "2026-05-01 14:30" in html
        # dark design tokens (no arbitrary values, no legacy card class)
        assert "bg-surface-raised" in html
        assert "text-text-primary" in html
        assert "class=\"card " not in html

    def test_entry_card_source_has_no_arbitrary_tailwind_values(self) -> None:
        """Static-source: migrated card carries no arbitrary Tailwind values."""
        src = (TEMPLATES / "_entry_card.html").read_text()
        assert "[#" not in src  # no bg-[#...] / text-[#...]
        assert "w-[" not in src
        assert "text-[" not in src


class TestAC2SearchFiltersToMatches:
    """AC2 / FR29: search by keyword or by service filters to matches."""

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_keyword_search_returns_matching_entries(
        self,
        mock_get_kb_service: MagicMock,
        mock_get_embedding_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service
        mock_embedding = MagicMock(spec=EmbeddingService)
        mock_embedding.is_configured.return_value = True
        mock_get_embedding_service.return_value = mock_embedding

        match = _make_entry("kb-1", "investigation", "Redis eviction storm")
        match.relevance_score = 0.91
        mock_kb_service.search_semantic.return_value = ([match], True)

        response = client.get("/knowledge/search?q=redis")
        body = response.data.decode()

        assert response.status_code == 200
        assert "Redis eviction storm" in body
        # the query drove a semantic search
        assert mock_kb_service.search_semantic.called
        assert mock_kb_service.search_semantic.call_args.kwargs["query"] == "redis"

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_service_filter_returns_filtered_entries(
        self, mock_get_kb_service: MagicMock, client: FlaskClient
    ) -> None:
        """Service filter with no keyword performs a filter-only search."""
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service
        mock_kb_service.list_recent_entries.return_value = [
            _make_entry("kb-1", "runbook", "API runbook", service="api"),
        ]

        response = client.get("/knowledge/search?service=api")
        body = response.data.decode()

        assert response.status_code == 200
        assert "API runbook" in body
        # filter-only search routed through list_recent_entries with the service
        assert mock_kb_service.list_recent_entries.call_args.kwargs["service"] == "api"

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_search_no_matches_shows_no_results_message(
        self,
        mock_get_kb_service: MagicMock,
        mock_get_embedding_service: MagicMock,
        client: FlaskClient,
    ) -> None:
        mock_kb_service = MagicMock()
        mock_get_kb_service.return_value = mock_kb_service
        mock_embedding = MagicMock(spec=EmbeddingService)
        mock_embedding.is_configured.return_value = True
        mock_get_embedding_service.return_value = mock_embedding
        mock_kb_service.search_semantic.return_value = ([], True)

        response = client.get("/knowledge/search?q=zzz-nothing")
        body = response.data.decode()

        assert response.status_code == 200
        assert "No results found" in body


class TestAC3EntryDetailShowsFR31Fields:
    """AC3 / FR31: detail shows root cause, resolution, affected services and the
    source investigation reference."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_entry_detail_renders_root_cause_resolution_affected_and_source(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = _make_entry(
            "kb-incident",
            "investigation",
            "Checkout 500s",
            content="## Full record\n\nDetails here.",
            service="checkout",
            root_cause="Connection pool exhausted under load",
            resolution="Raised pool size from 10 to 50 and added backpressure",
            affected_services=["checkout", "payments"],
        )
        mock_service.list_related_entries.return_value = []
        mock_service.get_entry_payload.return_value = {}
        mock_service.get_source_investigation.return_value = {
            "investigation_id": "inv-checkout-42",
            "relationship": "source",
        }
        mock_service.get_contributing_investigations.return_value = []

        response = client.get("/knowledge/kb-incident")
        body = response.data.decode()

        assert response.status_code == 200
        # FR31 — each required field surfaced as a labeled section
        assert "Root Cause" in body
        assert "Connection pool exhausted under load" in body
        assert "Resolution" in body
        assert "Raised pool size from 10 to 50" in body
        assert "Affected Services" in body
        assert "payments" in body
        # source investigation reference
        assert "Source Investigation" in body
        assert "inv-checkout-42" in body

    def test_kbentry_parses_fr31_fields_from_payload(self) -> None:
        """The model surfaces structured FR31 fields from the Qdrant payload,
        including resolution falling back to the recorded outcome."""
        entry = KBEntry.from_qdrant(
            "point-99",
            {
                "entry_id": "kb-x",
                "entry_type": "investigation",
                "title": "X",
                "root_cause": "bad config",
                "resolution_outcome": "resolved",
                "affected_services": ["a", "b"],
            },
        )
        assert entry.root_cause == "bad config"
        assert entry.resolution == "resolved"
        assert entry.affected_services == ["a", "b"]


class TestAC4EmptyState:
    """AC4: empty KB renders an explanatory empty state, not a blank page."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_empty_kb_renders_explanatory_empty_state(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.return_value = []
        mock_service.get_available_services.return_value = []
        mock_service.get_entry_types.return_value = []

        response = client.get("/knowledge/")
        body = response.data.decode()

        assert response.status_code == 200
        # explanatory copy (not a blank list)
        assert "No knowledge base entries yet" in body
        assert "import runbooks" in body.lower()
        # uses the shared empty_state component markup
        assert "empty-state" in body

    def test_entry_list_uses_empty_state_macro(self) -> None:
        """Static-source: the list partial imports + invokes the empty_state
        macro rather than an inline legacy div."""
        src = (TEMPLATES / "_entry_list.html").read_text()
        assert 'import empty_state' in src
        assert "empty_state(" in src
