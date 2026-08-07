"""Tests for Task 5.1 — BFF JSON API for the React Knowledge Base views.

Acceptance criteria (each `[T]` maps to a clearly-named test class):

[T1] GET /api/v1/knowledge/ returns JSON (not HTML); Content-Type is
     application/json; browse mode (no `q`) and search mode (`q` present)
     both return the expected `{query, entries, has_exact_matches, error}`
     shape, reusing `KBService`/`EmbeddingService` exactly as the Jinja
     `kb_index()`/`kb_search()` routes do.

[T2] GET /api/v1/knowledge/<entry_id> returns JSON (not HTML); Content-Type
     is application/json; response includes the full entry (including FR31's
     structured `root_cause`/`resolution`/`affected_services` fields and
     sanitized `content_html`), `related_entries`, and the bi-directional
     investigation links, mirroring `kb_entry()`.

Mocking follows this codebase's established convention for KB routes
(`tests/test_routes_knowledge.py`): `@patch("beeper_ui.routes.knowledge.get_kb_service")`
with a `MagicMock` — not `respx` (which is for the operator's HTTP API that
`investigations.py` calls; `KBService` talks to Qdrant directly, so there's
no HTTP boundary to intercept).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from flask.testing import FlaskClient

from beeper_ui.services.kb_service import KBEntry, KBServiceError

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_entry(
    entry_id: str = "kb-001",
    entry_type: str = "investigation",
    title: str = "checkout-service latency after deploy",
    content: str = (
        "## Root cause\n\nConnection pool exhaustion after a deploy.\n\n"
        "Some more detail padding this out."
    ),
    service: str | None = "checkout-service",
    root_cause: str | None = "Connection pool exhaustion",
    resolution: str | None = "Increased pool size and added backpressure",
    affected_services: list[str] | None = None,
) -> KBEntry:
    return KBEntry(
        id="point-1",
        entry_id=entry_id,
        entry_type=entry_type,
        title=title,
        content=content,
        service=service,
        created_at=datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, 10, 5, 0, tzinfo=timezone.utc),
        author="beeper",
        version=2,
        tags=["deploy", "latency"],
        auto_published=False,
        validation_status="human-confirmed",
        root_cause=root_cause,
        resolution=resolution,
        affected_services=affected_services or ["checkout-service", "frontend"],
    )


# ---------------------------------------------------------------------------
# [T1] GET /api/v1/knowledge/ — browse + search endpoint
# ---------------------------------------------------------------------------


class TestKnowledgeListEndpoint:
    """[T1] /api/v1/knowledge/ returns JSON with the expected shape (FR28/FR29)."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_returns_json_content_type(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.return_value = [_make_entry()]

        resp = client.get("/api/v1/knowledge/")

        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        assert "text/html" not in resp.content_type

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_no_html_in_body(self, mock_get_service: MagicMock, client: FlaskClient) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.return_value = [_make_entry()]

        resp = client.get("/api/v1/knowledge/")
        raw = resp.data.decode()

        assert "<html" not in raw
        assert "<!DOCTYPE" not in raw

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_browse_mode_no_query_uses_list_recent_entries(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """FR28 — no `q` param browses recent entries (kb_index's data path)."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.return_value = [_make_entry(entry_id="kb-browse")]

        resp = client.get("/api/v1/knowledge/")
        data = resp.get_json()

        assert data["query"] == ""
        assert len(data["entries"]) == 1
        assert data["entries"][0]["entry_id"] == "kb-browse"
        assert data["has_exact_matches"] is True
        assert data["error"] is None
        mock_service.list_recent_entries.assert_called_once()
        mock_service.search_semantic.assert_not_called()

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_browse_entry_shape(self, mock_get_service: MagicMock, client: FlaskClient) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.return_value = [_make_entry()]

        resp = client.get("/api/v1/knowledge/")
        elem = resp.get_json()["entries"][0]

        assert elem["entry_id"] == "kb-001"
        assert elem["entry_type"] == "investigation"
        assert elem["title"] == "checkout-service latency after deploy"
        assert elem["service"] == "checkout-service"
        assert elem["created_at"] == "2026-06-01T10:00:00+00:00"
        assert elem["author"] == "beeper"
        assert elem["version"] == 2
        assert elem["tags"] == ["deploy", "latency"]
        assert elem["validation_status"] == "human-confirmed"
        # Snippet is plain text (markdown stripped), not raw markdown syntax.
        assert "##" not in elem["snippet"]
        assert "Connection pool exhaustion" in elem["snippet"]
        # List/search entries never carry the full content or rendered HTML —
        # only the entry-detail endpoint does.
        assert "content" not in elem
        assert "content_html" not in elem

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_browse_empty_kb_returns_empty_array_not_error(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.return_value = []

        resp = client.get("/api/v1/knowledge/")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["entries"] == []
        assert data["error"] is None

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_search_mode_with_query_calls_semantic_search(
        self,
        mock_get_service: MagicMock,
        mock_get_embedding: MagicMock,
        client: FlaskClient,
    ) -> None:
        """FR29 — a `q` param performs semantic search via KBService + EmbeddingService."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_embedding = MagicMock()
        mock_embedding.is_configured.return_value = True
        mock_get_embedding.return_value = mock_embedding
        mock_service.search_semantic.return_value = ([_make_entry(entry_id="kb-search-hit")], True)

        resp = client.get("/api/v1/knowledge/?q=connection+pool")
        data = resp.get_json()

        assert data["query"] == "connection pool"
        assert len(data["entries"]) == 1
        assert data["entries"][0]["entry_id"] == "kb-search-hit"
        assert data["has_exact_matches"] is True
        mock_service.search_semantic.assert_called_once()
        call_kwargs = mock_service.search_semantic.call_args.kwargs
        assert call_kwargs["query"] == "connection pool"
        assert call_kwargs["embedding_service"] is mock_embedding
        mock_service.list_recent_entries.assert_not_called()

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_search_no_exact_matches_flag_passed_through(
        self,
        mock_get_service: MagicMock,
        mock_get_embedding: MagicMock,
        client: FlaskClient,
    ) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_embedding = MagicMock()
        mock_embedding.is_configured.return_value = True
        mock_get_embedding.return_value = mock_embedding
        mock_service.search_semantic.return_value = ([_make_entry()], False)

        resp = client.get("/api/v1/knowledge/?q=obscure+query")
        data = resp.get_json()

        assert data["has_exact_matches"] is False

    @patch("beeper_ui.routes.knowledge.get_embedding_service")
    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_search_not_configured_returns_soft_error(
        self,
        mock_get_service: MagicMock,
        mock_get_embedding: MagicMock,
        client: FlaskClient,
    ) -> None:
        """Missing OPENAI_API_KEY degrades gracefully (200 + error field), matching kb_search()."""
        mock_get_service.return_value = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.is_configured.return_value = False
        mock_get_embedding.return_value = mock_embedding

        resp = client.get("/api/v1/knowledge/?q=anything")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["entries"] == []
        assert data["error"] is not None
        assert "OPENAI_API_KEY" in data["error"]

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_browse_kb_service_error_returns_503(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.side_effect = KBServiceError("Qdrant unavailable")

        resp = client.get("/api/v1/knowledge/")
        data = resp.get_json()

        assert resp.status_code == 503
        assert data["error"] == "Qdrant unavailable"
        assert data["entries"] == []

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_entry_type_and_service_filters_forwarded(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.return_value = []

        resp = client.get("/api/v1/knowledge/?entry_type=runbook&service=checkout-service")

        assert resp.status_code == 200
        mock_service.list_recent_entries.assert_called_once()
        call_kwargs = mock_service.list_recent_entries.call_args.kwargs
        assert call_kwargs["entry_type"] == "runbook"
        assert call_kwargs["service"] == "checkout-service"

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_invalid_entry_type_filter_ignored(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_recent_entries.return_value = []

        resp = client.get("/api/v1/knowledge/?entry_type=__bogus__")

        assert resp.status_code == 200
        call_kwargs = mock_service.list_recent_entries.call_args.kwargs
        assert call_kwargs["entry_type"] is None


# ---------------------------------------------------------------------------
# [T2] GET /api/v1/knowledge/<entry_id> — entry detail endpoint
# ---------------------------------------------------------------------------


class TestKnowledgeEntryDetailEndpoint:
    """[T2] /api/v1/knowledge/<entry_id> returns JSON with full entry detail (FR31)."""

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_returns_json_content_type(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = _make_entry()
        mock_service.list_related_entries.return_value = []
        mock_service.get_entry_payload.return_value = {}
        mock_service.get_source_investigation.return_value = None
        mock_service.get_contributing_investigations.return_value = []

        resp = client.get("/api/v1/knowledge/kb-001")

        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        assert "text/html" not in resp.content_type

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_no_html_in_body(self, mock_get_service: MagicMock, client: FlaskClient) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = _make_entry()
        mock_service.list_related_entries.return_value = []
        mock_service.get_entry_payload.return_value = {}
        mock_service.get_source_investigation.return_value = None
        mock_service.get_contributing_investigations.return_value = []

        resp = client.get("/api/v1/knowledge/kb-001")
        raw = resp.data.decode()

        assert "<!DOCTYPE" not in raw
        # `content_html` legitimately contains rendered <p>/<h2> tags — assert
        # no *page* chrome leaked through instead of a blanket "<" ban.
        assert "<html" not in raw
        assert "<body" not in raw

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_includes_entry_fields_and_sanitized_content_html(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = _make_entry(
            content="## Heading\n\nSome *markdown* body.\n\n<script>alert(1)</script>"
        )
        mock_service.list_related_entries.return_value = []
        mock_service.get_entry_payload.return_value = {}
        mock_service.get_source_investigation.return_value = None
        mock_service.get_contributing_investigations.return_value = []

        resp = client.get("/api/v1/knowledge/kb-001")
        entry = resp.get_json()["entry"]

        assert entry["entry_id"] == "kb-001"
        assert entry["title"] == "checkout-service latency after deploy"
        assert entry["version"] == 2
        # Rendered as sanitized HTML, not raw markdown.
        assert "<h2>Heading</h2>" in entry["content_html"]
        # XSS protection carried through from the existing render_markdown() sanitizer.
        assert "<script>" not in entry["content_html"]

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_includes_fr31_structured_incident_fields(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """FR31 — root_cause/resolution/affected_services surface verbatim, not re-derived."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = _make_entry(
            root_cause="Connection pool exhaustion",
            resolution="Increased pool size",
            affected_services=["checkout-service", "frontend"],
        )
        mock_service.list_related_entries.return_value = []
        mock_service.get_entry_payload.return_value = {}
        mock_service.get_source_investigation.return_value = None
        mock_service.get_contributing_investigations.return_value = []

        resp = client.get("/api/v1/knowledge/kb-001")
        entry = resp.get_json()["entry"]

        assert entry["root_cause"] == "Connection pool exhaustion"
        assert entry["resolution"] == "Increased pool size"
        assert entry["affected_services"] == ["checkout-service", "frontend"]

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_includes_related_entries(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = _make_entry()
        mock_service.list_related_entries.return_value = [
            _make_entry(entry_id="kb-related-1", title="Related one"),
            _make_entry(entry_id="kb-related-2", title="Related two"),
        ]
        mock_service.get_entry_payload.return_value = {}
        mock_service.get_source_investigation.return_value = None
        mock_service.get_contributing_investigations.return_value = []

        resp = client.get("/api/v1/knowledge/kb-001")
        related = resp.get_json()["related_entries"]

        assert len(related) == 2
        assert related[0]["entry_id"] == "kb-related-1"
        assert related[1]["title"] == "Related two"

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_includes_source_and_contributing_investigation_links(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = _make_entry()
        mock_service.list_related_entries.return_value = []
        mock_service.get_entry_payload.return_value = {"source_investigation_id": "inv-source-abc"}
        mock_service.get_source_investigation.return_value = {
            "investigation_id": "inv-source-abc",
            "relationship": "source",
        }
        mock_service.get_contributing_investigations.return_value = [
            {"investigation_id": "inv-contrib-1", "relationship": "contributing"},
        ]

        resp = client.get("/api/v1/knowledge/kb-001")
        data = resp.get_json()

        assert data["source_investigation"] == {
            "investigation_id": "inv-source-abc",
            "relationship": "source",
        }
        assert data["contributing_investigations"] == [
            {"investigation_id": "inv-contrib-1", "relationship": "contributing"},
        ]

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_not_found_returns_404(self, mock_get_service: MagicMock, client: FlaskClient) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = None

        resp = client.get("/api/v1/knowledge/kb-missing")

        assert resp.status_code == 404
        assert resp.get_json()["error"] == "not_found"

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_kb_service_error_on_get_entry_returns_503(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.side_effect = KBServiceError("Qdrant unavailable")

        resp = client.get("/api/v1/knowledge/kb-001")

        assert resp.status_code == 503
        assert resp.get_json()["error"] == "Qdrant unavailable"

    @patch("beeper_ui.routes.knowledge.get_kb_service")
    def test_related_entries_failure_degrades_gracefully(
        self, mock_get_service: MagicMock, client: FlaskClient
    ) -> None:
        """A related-entries lookup failure doesn't fail the whole detail response."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_entry.return_value = _make_entry()
        mock_service.list_related_entries.side_effect = KBServiceError("scan failed")
        mock_service.get_entry_payload.return_value = {}
        mock_service.get_source_investigation.return_value = None
        mock_service.get_contributing_investigations.return_value = []

        resp = client.get("/api/v1/knowledge/kb-001")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["related_entries"] == []
        assert data["entry"]["entry_id"] == "kb-001"
