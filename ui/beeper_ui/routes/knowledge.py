"""Knowledge Base routes for Beeper UI."""

import os
import re

from flask import Blueprint, render_template, request

from beeper_ui.services.embedding_service import get_embedding_service
from beeper_ui.services.kb_service import KBEntry, KBService, KBServiceError

knowledge_bp = Blueprint("knowledge", __name__, url_prefix="/knowledge")

# Maximum query length (OpenAI embedding models have ~8k token limit, ~4 chars/token average)
MAX_QUERY_LENGTH = 500


def sanitize_query(query: str) -> str:
    """Sanitize search query for safe processing.

    Args:
        query: Raw query string from user input

    Returns:
        Sanitized query string, limited in length and stripped of tags.
    """
    if not query:
        return ""

    # Strip whitespace
    cleaned = query.strip()

    # Remove HTML/script tags
    cleaned = re.sub(r'<[^>]+>', '', cleaned)

    # Limit length
    if len(cleaned) > MAX_QUERY_LENGTH:
        cleaned = cleaned[:MAX_QUERY_LENGTH]

    return cleaned


def get_kb_service() -> KBService:
    """Get configured KBService instance."""
    return KBService(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )


@knowledge_bp.route("/")
def kb_index() -> str:
    """Display the Knowledge Base wiki index.

    Supports optional query parameters:
    - entry_type: Filter by entry type (investigation, runbook, correction)
    - service: Filter by service name

    For HTMX requests (filtering), returns only the entry list partial.
    For full page requests, returns the complete page.
    """
    entry_type = request.args.get("entry_type")
    service = request.args.get("service")

    service_client = get_kb_service()
    error_message: str | None = None
    entries: list[KBEntry] = []
    services: list[str] = []
    entry_types: list[str] = []

    try:
        entries = service_client.list_recent_entries(
            limit=20, entry_type=entry_type, service=service
        )
        services = service_client.get_available_services()
        entry_types = service_client.get_entry_types()
    except KBServiceError as e:
        error_message = str(e)

    # Check if this is an HTMX request (for partial updates)
    if request.headers.get("HX-Request"):
        return render_template(
            "knowledge/_entry_list.html",
            entries=entries,
            error_message=error_message,
        )

    return render_template(
        "knowledge/index.html",
        entries=entries,
        services=services,
        entry_types=entry_types,
        selected_service=service,
        selected_entry_type=entry_type,
        error_message=error_message,
    )


# NOTE: Static routes (/search) must be defined BEFORE dynamic routes (/<entry_id>)
# to ensure proper route matching in Flask.


@knowledge_bp.route("/search")
def kb_search() -> str:
    """Search the Knowledge Base using semantic similarity.

    Query parameters:
    - q: Search query (natural language)
    - entry_type: Optional filter by entry type
    - service: Optional filter by service name

    Returns:
        HTMX partial with search results.
    """
    query = sanitize_query(request.args.get("q", ""))
    entry_type = request.args.get("entry_type")
    service = request.args.get("service")

    # Return empty if no query
    if not query:
        return render_template(
            "knowledge/_search_results.html",
            query="",
            entries=[],
            has_exact_matches=True,
        )

    service_client = get_kb_service()
    entries: list[KBEntry] = []
    has_exact_matches = True

    try:
        # Get the global embedding service instance
        embedding_service = get_embedding_service()

        # Check if embedding service is configured
        if not embedding_service.is_configured():
            return render_template(
                "knowledge/_search_results.html",
                query=query,
                entries=[],
                has_exact_matches=True,
                error_message="Search not configured. Set OPENAI_API_KEY to enable.",
            )

        entries, has_exact_matches = service_client.search_semantic(
            query=query,
            limit=10,
            entry_type=entry_type if entry_type else None,
            service=service if service else None,
            embedding_service=embedding_service,
        )
    except KBServiceError as e:
        return render_template(
            "knowledge/_search_results.html",
            query=query,
            entries=[],
            has_exact_matches=True,
            error_message=str(e),
        )

    return render_template(
        "knowledge/_search_results.html",
        query=query,
        entries=entries,
        has_exact_matches=has_exact_matches,
    )


@knowledge_bp.route("/<entry_id>")
def kb_entry(entry_id: str) -> tuple[str, int] | str:
    """Display a single KB entry.

    Args:
        entry_id: The unique identifier of the entry

    Returns:
        Rendered entry page or 404 error.
    """
    service_client = get_kb_service()
    error_message: str | None = None
    entry: KBEntry | None = None
    related_entries: list[KBEntry] = []

    try:
        entry = service_client.get_entry(entry_id)
        if entry:
            related_entries = service_client.list_related_entries(
                entry_id=entry_id, service=entry.service, limit=5
            )
    except KBServiceError as e:
        error_message = str(e)

    if not entry and not error_message:
        return (
            render_template(
                "knowledge/entry.html",
                entry=None,
                related_entries=[],
                error_message=f"Entry '{entry_id}' not found",
            ),
            404,
        )

    return render_template(
        "knowledge/entry.html",
        entry=entry,
        related_entries=related_entries,
        error_message=error_message,
    )


@knowledge_bp.route("/<entry_id>/related")
def kb_related(entry_id: str) -> str:
    """Get related entries for HTMX partial loading.

    Args:
        entry_id: The unique identifier of the entry

    Returns:
        Rendered partial with related entries.
    """
    service_client = get_kb_service()
    service = request.args.get("service")
    related_entries: list[KBEntry] = []

    try:
        related_entries = service_client.list_related_entries(
            entry_id=entry_id, service=service, limit=5
        )
    except KBServiceError:
        pass  # Silently fail for related entries

    return render_template(
        "knowledge/_related.html",
        related_entries=related_entries,
        current_entry_id=entry_id,
    )
