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

Task 6.3 (Jinja retirement, D13/D14): the KB index/search/entry-detail pages
(``GET /knowledge/``, ``GET /knowledge/search``, ``GET /knowledge/<id>``) are
retired — they now 302-redirect to the React app (``/app/knowledge...``) via
the ``react_registry`` before-request hook, so their route-level render
assertions for AC1 (index), AC2 (search) and AC4 (empty state) no longer
apply here and were removed. What remains: AC1/AC3 coverage of the
``_entry_card.html`` component and ``KBEntry`` model parsing, which are still
exercised outside the retired pages (e.g. ``service_knowledge.html``).
Route-level coverage of AC1/AC2/AC3/AC4 now lives in the React app's own
tests.
"""

from datetime import datetime, timezone
from pathlib import Path

from flask import Flask

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
    """AC1 / FR28: KB index lists entries with service, title and date.

    The route-level render check (``GET /knowledge/``) was removed under
    Task 6.3 — the index page is retired and now redirects to the React app.
    What remains proves the underlying ``_entry_card.html`` component (still
    used by the live ``service_knowledge.html`` view) surfaces these fields.
    """

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


class TestAC3EntryDetailShowsFR31Fields:
    """AC3 / FR31: detail shows root cause, resolution, affected services and the
    source investigation reference.

    The route-level render check (``GET /knowledge/<id>``) was removed under
    Task 6.3 — the entry detail page is retired and now redirects to the
    React app. What remains proves the ``KBEntry`` model correctly parses
    these FR31 fields from the Qdrant payload, independent of rendering.
    """

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


# AC4 (empty KB renders an explanatory empty state) was covered here via
# `GET /knowledge/` and the now-deleted `_entry_list.html` partial. Both the
# index route and that partial were retired under Task 6.3 — the index page
# now redirects to the React app, which owns the empty-state rendering.
# There is no remaining Python-level surface for AC4; see the React app's
# own tests for empty-state coverage.
