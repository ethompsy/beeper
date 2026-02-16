"""Knowledge Base routes for Beeper UI."""

import os
import re

from flask import Blueprint, render_template, request
from werkzeug.utils import secure_filename

from beeper_ui.services.embedding_service import get_embedding_service
from beeper_ui.services.import_service import (
    ImportResult,
    parse_markdown_file,
    parse_tags,
    validate_import_data,
)
from beeper_ui.services.kb_service import (
    KBEntry,
    KBService,
    KBServiceError,
    parse_date_range,
)

knowledge_bp = Blueprint("knowledge", __name__, url_prefix="/knowledge")

# Maximum query length (OpenAI embedding models have ~8k token limit, ~4 chars/token average)
MAX_QUERY_LENGTH = 500

# Valid entry types for filtering (security: prevent arbitrary values)
VALID_ENTRY_TYPES = {"investigation", "runbook", "correction"}

# Allowed file extensions for import
ALLOWED_EXTENSIONS = {"md", "txt", "json", "markdown"}


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed.

    Args:
        filename: The filename to check

    Returns:
        True if extension is allowed, False otherwise.
    """
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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


def validate_entry_type(entry_type: str | None) -> str | None:
    """Validate entry_type filter against known types.

    Args:
        entry_type: Entry type from query parameter

    Returns:
        Valid entry type or None if invalid/empty.
    """
    if not entry_type:
        return None
    if entry_type in VALID_ENTRY_TYPES:
        return entry_type
    return None


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
    - date_range: Filter by date range (today, 7d, 30d, 90d)
    - q: Search query (preserved for URL state)

    For HTMX requests (filtering), returns only the entry list partial.
    For full page requests, returns the complete page.
    """
    entry_type = validate_entry_type(request.args.get("entry_type"))
    service = request.args.get("service")
    date_range = request.args.get("date_range")
    query = request.args.get("q", "")

    # Parse date range
    date_from, date_to = parse_date_range(date_range or "")

    service_client = get_kb_service()
    error_message: str | None = None
    entries: list[KBEntry] = []
    services: list[str] = []
    entry_types: list[str] = []

    try:
        entries = service_client.list_recent_entries(
            limit=20,
            entry_type=entry_type,
            service=service,
            date_from=date_from,
            date_to=date_to,
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

    # Calculate if any filter is active (for active filter chips display)
    any_filter_active = bool(entry_type or service or date_range)

    return render_template(
        "knowledge/index.html",
        entries=entries,
        services=services,
        entry_types=entry_types,
        selected_service=service,
        selected_entry_type=entry_type,
        selected_date_range=date_range,
        query=query,
        error_message=error_message,
        any_filter_active=any_filter_active,
    )


# NOTE: Static routes (/search, /import) must be defined BEFORE dynamic routes (/<entry_id>)
# to ensure proper route matching in Flask.


@knowledge_bp.route("/import", methods=["GET", "POST"])
def kb_import() -> str:
    """Import runbooks into the Knowledge Base.

    GET: Display the import form.
    POST: Process the import (file upload or paste).

    Returns:
        Rendered import page or import result partial.
    """
    service_client = get_kb_service()

    if request.method == "GET":
        # Get available services for dropdown
        try:
            services = service_client.get_available_services()
        except KBServiceError:
            services = []

        return render_template(
            "knowledge/import.html",
            services=services,
        )

    # POST: Process import
    import_mode = request.form.get("import_mode", "paste")
    service = request.form.get("service") or None
    tags_string = request.form.get("tags", "")
    tags = parse_tags(tags_string)
    duplicate_action = request.form.get("duplicate_action")

    # Get available services for re-rendering form on error
    try:
        services = service_client.get_available_services()
    except KBServiceError:
        services = []

    # Process based on import mode
    if import_mode == "file":
        # File upload
        file = request.files.get("file")
        if not file or not file.filename:
            return render_template(
                "knowledge/_import_result.html",
                result=ImportResult(
                    success=False,
                    error="No file selected. Please select a file to upload.",
                ),
                services=services,
            )

        filename = secure_filename(file.filename)
        if not allowed_file(filename):
            return render_template(
                "knowledge/_import_result.html",
                result=ImportResult(
                    success=False,
                    error=f"File type not allowed. Allowed extensions: {', '.join(ALLOWED_EXTENSIONS)}",
                ),
                services=services,
            )

        try:
            content = file.read().decode("utf-8")
        except UnicodeDecodeError:
            return render_template(
                "knowledge/_import_result.html",
                result=ImportResult(
                    success=False,
                    error="File must be a text file (UTF-8 encoded).",
                ),
                services=services,
            )

        # Parse markdown file
        parsed = parse_markdown_file(content, filename)
        title = parsed["title"]
        content = parsed["content"]

        # Use file metadata if not overridden by form
        if not service and parsed["service"]:
            service = parsed["service"]
        if not tags and parsed["tags"]:
            tags = parsed["tags"]

    else:
        # Paste mode
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()

    # Validate import data
    errors = validate_import_data(title, content, service, tags)
    if errors:
        return render_template(
            "knowledge/_import_result.html",
            result=ImportResult(
                success=False,
                error="; ".join(errors),
            ),
            services=services,
        )

    # Check for duplicates (unless user already chose an action)
    if not duplicate_action:
        duplicate = service_client.check_duplicate(
            title=title,
            service=service,
            entry_type="runbook",
        )
        if duplicate:
            return render_template(
                "knowledge/_import_duplicate.html",
                duplicate=duplicate,
                title=title,
                content=content,
                service=service,
                tags=",".join(tags),
                services=services,
            )

    # Handle duplicate action
    if duplicate_action == "skip":
        return render_template(
            "knowledge/_import_result.html",
            result=ImportResult(
                success=False,
                title=title,
                error="Import skipped (duplicate entry exists).",
            ),
            services=services,
        )
    elif duplicate_action == "update":
        # Update existing entry using entry_id from hidden form field
        duplicate_entry_id = request.form.get("duplicate_entry_id")
        if duplicate_entry_id:
            try:
                embedding_service = get_embedding_service()
                if not embedding_service.is_configured():
                    return render_template(
                        "knowledge/_import_result.html",
                        result=ImportResult(
                            success=False,
                            error="Embedding service not configured. Set OPENAI_API_KEY to enable imports.",
                        ),
                        services=services,
                    )
                new_version = service_client.update_entry(
                    entry_id=duplicate_entry_id,
                    content=content,
                    tags=tags,
                    author="import",
                    embedding_service=embedding_service,
                )
                return render_template(
                    "knowledge/_import_result.html",
                    result=ImportResult(
                        success=True,
                        entry_id=duplicate_entry_id,
                        title=title,
                        warnings=[f"Updated existing entry (version {new_version})"],
                    ),
                    services=services,
                )
            except KBServiceError as e:
                return render_template(
                    "knowledge/_import_result.html",
                    result=ImportResult(
                        success=False,
                        title=title,
                        error=str(e),
                    ),
                    services=services,
                )

    # Create new entry (default or duplicate_action == "create")
    try:
        embedding_service = get_embedding_service()
        if not embedding_service.is_configured():
            return render_template(
                "knowledge/_import_result.html",
                result=ImportResult(
                    success=False,
                    error="Embedding service not configured. Set OPENAI_API_KEY to enable imports.",
                ),
                services=services,
            )

        entry_id = service_client.create_entry(
            title=title,
            content=content,
            entry_type="runbook",
            service=service,
            tags=tags,
            author="import",
            embedding_service=embedding_service,
        )

        return render_template(
            "knowledge/_import_result.html",
            result=ImportResult(
                success=True,
                entry_id=entry_id,
                title=title,
            ),
            services=services,
        )

    except KBServiceError as e:
        return render_template(
            "knowledge/_import_result.html",
            result=ImportResult(
                success=False,
                title=title,
                error=str(e),
            ),
            services=services,
        )


@knowledge_bp.route("/search")
def kb_search() -> str:
    """Search the Knowledge Base using semantic similarity and/or filters.

    Query parameters:
    - q: Search query (natural language, optional)
    - entry_type: Optional filter by entry type
    - service: Optional filter by service name
    - date_range: Optional filter by date range (today, 7d, 30d, 90d)

    Returns:
        HTMX partial with search results.

    Note:
        If no query is provided but filters are active, performs filter-only search.
        If query is provided, performs semantic search with optional filters.
    """
    query = sanitize_query(request.args.get("q", ""))
    entry_type = validate_entry_type(request.args.get("entry_type"))
    service = request.args.get("service") or None
    date_range = request.args.get("date_range") or None

    # Parse date range
    date_from, date_to = parse_date_range(date_range or "")

    # Check if any filter is active
    any_filter_active = bool(entry_type or service or date_range)

    # Return empty if no query and no filters
    if not query and not any_filter_active:
        return render_template(
            "knowledge/_search_results.html",
            query="",
            entries=[],
            has_exact_matches=True,
            selected_entry_type=entry_type,
            selected_service=service,
            selected_date_range=date_range,
            any_filter_active=False,
        )

    service_client = get_kb_service()
    entries: list[KBEntry] = []
    has_exact_matches = True

    try:
        if query:
            # Semantic search with optional filters
            embedding_service = get_embedding_service()

            # Check if embedding service is configured
            if not embedding_service.is_configured():
                return render_template(
                    "knowledge/_search_results.html",
                    query=query,
                    entries=[],
                    has_exact_matches=True,
                    selected_entry_type=entry_type,
                    selected_service=service,
                    selected_date_range=date_range,
                    any_filter_active=any_filter_active,
                    error_message="Search not configured. Set OPENAI_API_KEY to enable.",
                )

            entries, has_exact_matches = service_client.search_semantic(
                query=query,
                limit=10,
                entry_type=entry_type,
                service=service,
                date_from=date_from,
                date_to=date_to,
                embedding_service=embedding_service,
            )
        else:
            # Filter-only search (no semantic query)
            entries = service_client.list_recent_entries(
                limit=20,
                entry_type=entry_type,
                service=service,
                date_from=date_from,
                date_to=date_to,
            )
            has_exact_matches = True  # No semantic scoring for filter-only

    except KBServiceError as e:
        return render_template(
            "knowledge/_search_results.html",
            query=query,
            entries=[],
            has_exact_matches=True,
            selected_entry_type=entry_type,
            selected_service=service,
            selected_date_range=date_range,
            any_filter_active=any_filter_active,
            error_message=str(e),
        )

    return render_template(
        "knowledge/_search_results.html",
        query=query,
        entries=entries,
        has_exact_matches=has_exact_matches,
        selected_entry_type=entry_type,
        selected_service=service,
        selected_date_range=date_range,
        any_filter_active=any_filter_active,
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
