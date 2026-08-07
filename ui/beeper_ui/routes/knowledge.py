"""Knowledge Base routes for Beeper UI."""

import logging
import os
import re
from typing import Any

from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from beeper_ui.middleware.permissions import require_role
from beeper_ui.services.correction_service import (
    CorrectionServiceError,
    get_correction_service,
)
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
    generate_diff,
    parse_date_range,
)
from beeper_ui.services.learning_service import (
    LearningServiceError,
    get_learning_service,
)
from beeper_ui.utils.markdown_utils import render_markdown, strip_markdown

logger = logging.getLogger(__name__)

knowledge_bp = Blueprint("knowledge", __name__, url_prefix="/knowledge")

# JSON API blueprint (Task 5.1). Kept separate from the HTML `knowledge_bp`
# so it can live under the /api/v1 prefix the React KB browse/search +
# entry-detail views fetch — mirrors the investigations_api_bp pattern in
# `ui/beeper_ui/routes/investigations.py` (Task 1.6).
knowledge_api_bp = Blueprint("knowledge_api", __name__, url_prefix="/api/v1/knowledge")

# Maximum query length (OpenAI embedding models have ~8k token limit, ~4 chars/token average)
MAX_QUERY_LENGTH = 500

# Valid entry types for filtering (security: prevent arbitrary values)
VALID_ENTRY_TYPES = {"investigation", "runbook", "correction", "proven_fix"}

# Valid validation statuses (from KnowledgeEntry schema)
VALID_VALIDATION_STATUSES = {"AI-generated", "human-confirmed", "proven", "corrected"}

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
    cleaned = re.sub(r"<[^>]+>", "", cleaned)

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
                    error=(
                        "File type not allowed. Allowed extensions: "
                        f"{', '.join(ALLOWED_EXTENSIONS)}"
                    ),
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
                            error=(
                                "Embedding service not configured. "
                                "Set OPENAI_API_KEY to enable imports."
                            ),
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


def _compute_change_summaries(versions: list[dict]) -> None:
    """Compute change summaries by comparing consecutive versions in-place.

    Adds a 'change_summary' key to each version dict. The oldest version
    gets 'Initial version'. Versions are expected in descending order.
    """
    # Work from oldest to newest for comparison
    sorted_asc = sorted(versions, key=lambda v: v["version"])

    for i, v in enumerate(sorted_asc):
        if i == 0:
            v["change_summary"] = "Initial version"
            continue

        prev = sorted_asc[i - 1]
        changes: list[str] = []

        if v.get("title") != prev.get("title"):
            changes.append("Title updated")

        content_diff = v.get("content_length", 0) - prev.get("content_length", 0)
        if content_diff > 0:
            changes.append(f"{content_diff} chars added")
        elif content_diff < 0:
            changes.append(f"{abs(content_diff)} chars removed")

        if v.get("tags", []) != prev.get("tags", []):
            changes.append("Tags updated")

        if v.get("service") != prev.get("service"):
            changes.append("Service changed")

        v["change_summary"] = "; ".join(changes) if changes else "No detected changes"


@knowledge_bp.route("/<entry_id>/history")
def kb_history(entry_id: str) -> tuple[str, int] | str:
    """Display version history for a KB entry.

    Args:
        entry_id: The unique identifier of the entry

    Returns:
        Rendered history page or 404 error.
    """
    service_client = get_kb_service()

    try:
        entry = service_client.get_entry(entry_id)
    except KBServiceError as e:
        return render_template(
            "knowledge/history.html",
            entry=None,
            versions=[],
            error_message=str(e),
        )

    if not entry:
        return (
            render_template(
                "knowledge/history.html",
                entry=None,
                versions=[],
                error_message=f"Entry '{entry_id}' not found",
            ),
            404,
        )

    try:
        versions = service_client.list_versions(entry_id)
    except KBServiceError:
        versions = []

    # Include the current version at the top of the list (from live entry)
    current_version = {
        "version": entry.version,
        "author": entry.author,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
        "title": entry.title,
        "content_length": len(entry.content) if entry.content else 0,
        "tags": entry.tags,
        "service": entry.service,
        "is_current": True,
    }

    # Merge: add is_current=False to snapshot versions, filter out duplicates
    snapshot_versions = [
        {**v, "is_current": False} for v in versions if v["version"] != entry.version
    ]
    all_versions = [current_version] + snapshot_versions

    # Compute change summaries by comparing consecutive versions
    _compute_change_summaries(all_versions)

    return render_template(
        "knowledge/history.html",
        entry=entry,
        versions=all_versions,
    )


@knowledge_bp.route("/<entry_id>/version/<int:version_num>")
def kb_version(entry_id: str, version_num: int) -> tuple[str, int] | str:
    """View a specific version of a KB entry.

    Args:
        entry_id: The unique identifier of the entry
        version_num: The version number to view

    Returns:
        Rendered version page or 404 error.
    """
    service_client = get_kb_service()

    try:
        entry = service_client.get_entry(entry_id)
    except KBServiceError as e:
        return render_template(
            "knowledge/version.html",
            entry=None,
            version_data=None,
            error_message=str(e),
        )

    if not entry:
        return (
            render_template(
                "knowledge/version.html",
                entry=None,
                version_data=None,
                error_message=f"Entry '{entry_id}' not found",
            ),
            404,
        )

    try:
        version_data = service_client.get_version(entry_id, version_num)
    except KBServiceError as e:
        return render_template(
            "knowledge/version.html",
            entry=entry,
            version_data=None,
            error_message=str(e),
        )

    if not version_data:
        return (
            render_template(
                "knowledge/version.html",
                entry=entry,
                version_data=None,
                error_message=f"Version {version_num} not found",
            ),
            404,
        )

    # Compute actual prev/next version numbers from version list
    try:
        versions = service_client.list_versions(entry_id)
        version_numbers = sorted(v["version"] for v in versions)
        # Include current live version if not in snapshots
        if entry.version not in version_numbers:
            version_numbers.append(entry.version)
            version_numbers.sort()
        idx = version_numbers.index(version_num) if version_num in version_numbers else -1
        prev_version = version_numbers[idx - 1] if idx > 0 else None
        next_version = version_numbers[idx + 1] if 0 <= idx < len(version_numbers) - 1 else None
    except (KBServiceError, ValueError):
        prev_version = None
        next_version = None

    return render_template(
        "knowledge/version.html",
        entry=entry,
        version_data=version_data,
        current_version=entry.version,
        prev_version=prev_version,
        next_version=next_version,
    )


@knowledge_bp.route("/<entry_id>/diff/<int:from_version>/<int:to_version>")
def kb_diff(entry_id: str, from_version: int, to_version: int) -> tuple[str, int] | str:
    """Compare two versions of a KB entry.

    Args:
        entry_id: The unique identifier of the entry
        from_version: The older version number
        to_version: The newer version number

    Returns:
        Rendered diff page or 404 error.
    """
    service_client = get_kb_service()

    try:
        entry = service_client.get_entry(entry_id)
    except KBServiceError as e:
        return render_template(
            "knowledge/diff.html",
            entry=None,
            error_message=str(e),
        )

    if not entry:
        return (
            render_template(
                "knowledge/diff.html",
                entry=None,
                error_message=f"Entry '{entry_id}' not found",
            ),
            404,
        )

    # Helper: build version payload from live entry (current version isn't
    # stored in knowledge_versions until the next update overwrites it).
    def _entry_as_version(e: KBEntry) -> dict:
        return {
            "entry_id": e.entry_id,
            "version": e.version,
            "title": e.title,
            "content": e.content,
            "author": e.author,
            "updated_at": e.updated_at.isoformat() if e.updated_at else None,
            "entry_type": e.entry_type,
            "service": e.service,
            "tags": e.tags,
        }

    try:
        from_data = service_client.get_version(entry_id, from_version)
    except KBServiceError as e:
        return render_template(
            "knowledge/diff.html",
            entry=entry,
            error_message=str(e),
        )

    if not from_data and entry.version == from_version:
        from_data = _entry_as_version(entry)

    if not from_data:
        return (
            render_template(
                "knowledge/diff.html",
                entry=entry,
                error_message=f"Version {from_version} not found",
            ),
            404,
        )

    try:
        to_data = service_client.get_version(entry_id, to_version)
    except KBServiceError as e:
        return render_template(
            "knowledge/diff.html",
            entry=entry,
            error_message=str(e),
        )

    if not to_data and entry.version == to_version:
        to_data = _entry_as_version(entry)

    if not to_data:
        return (
            render_template(
                "knowledge/diff.html",
                entry=entry,
                error_message=f"Version {to_version} not found",
            ),
            404,
        )

    diff_data = generate_diff(
        from_data.get("content", ""),
        to_data.get("content", ""),
    )

    return render_template(
        "knowledge/diff.html",
        entry=entry,
        from_version=from_data,
        to_version=to_data,
        hunks=diff_data["hunks"],
        has_changes=diff_data["has_changes"],
        summary=diff_data["summary"],
    )


@knowledge_bp.route("/<entry_id>/restore/<int:version_num>", methods=["POST"])
def kb_restore(entry_id: str, version_num: int) -> str:
    """Restore a previous version of a KB entry.

    Creates a new version with the old content.

    Args:
        entry_id: The unique identifier of the entry
        version_num: The version number to restore

    Returns:
        Rendered restore result partial.
    """
    service_client = get_kb_service()

    # Check embedding service
    embedding_service = get_embedding_service()
    if not embedding_service.is_configured():
        return render_template(
            "knowledge/_restore_result.html",
            error="Embedding service not configured. Set OPENAI_API_KEY to enable restoring.",
        )

    try:
        version_data = service_client.get_version(entry_id, version_num)
    except KBServiceError as e:
        return render_template(
            "knowledge/_restore_result.html",
            error=str(e),
        )

    if not version_data:
        return render_template(
            "knowledge/_restore_result.html",
            error=f"Version {version_num} not found",
        )

    try:
        new_version = service_client.update_entry(
            entry_id=entry_id,
            title=version_data.get("title"),
            content=version_data.get("content"),
            service=version_data.get("service"),
            tags=version_data.get("tags"),
            author="restore",
            embedding_service=embedding_service,
        )
        return render_template(
            "knowledge/_restore_result.html",
            success=True,
            entry_id=entry_id,
            restored_version=version_num,
            new_version=new_version,
        )
    except KBServiceError as e:
        return render_template(
            "knowledge/_restore_result.html",
            error=str(e),
        )


@knowledge_bp.route("/<entry_id>/edit", methods=["GET", "POST"])
def kb_edit(entry_id: str) -> tuple[str, int] | str:
    """Edit a KB entry.

    GET: Display the edit form populated with entry data.
    POST: Validate and save changes.

    Args:
        entry_id: The unique identifier of the entry

    Returns:
        Rendered edit page, edit result partial, or 404 error.
    """
    service_client = get_kb_service()

    try:
        services = service_client.get_available_services()
    except KBServiceError:
        services = []

    try:
        entry_types = service_client.get_entry_types()
        # Ensure proven_fix is included (used in per-service knowledge grouping)
        if "proven_fix" not in entry_types:
            entry_types = sorted(set(entry_types) | {"proven_fix"})
    except KBServiceError:
        entry_types = sorted(["correction", "investigation", "proven_fix", "runbook"])

    if request.method == "GET":
        try:
            entry = service_client.get_entry(entry_id)
        except KBServiceError as e:
            return (
                render_template(
                    "knowledge/edit.html",
                    entry=None,
                    services=services,
                    entry_types=entry_types,
                    error_message=str(e),
                ),
                200,
            )

        if not entry:
            return (
                render_template(
                    "knowledge/edit.html",
                    entry=None,
                    services=services,
                    entry_types=entry_types,
                    error_message=f"Entry '{entry_id}' not found",
                ),
                404,
            )

        return render_template(
            "knowledge/edit.html",
            entry=entry,
            services=services,
            entry_types=entry_types,
        )

    # POST: Save changes
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    service = request.form.get("service") or None
    tags_string = request.form.get("tags", "")
    tags = parse_tags(tags_string)
    form_version = request.form.get("version", "")
    raw_entry_type = request.form.get("entry_type") or None
    # Validate entry_type against allowed values (reject arbitrary user input)
    new_entry_type = raw_entry_type if raw_entry_type in VALID_ENTRY_TYPES else None

    # Validate
    errors = validate_import_data(title, content, service, tags)
    if errors:
        return render_template(
            "knowledge/_edit_result.html",
            error="; ".join(errors),
        )

    # Check embedding service
    embedding_service = get_embedding_service()
    if not embedding_service.is_configured():
        return render_template(
            "knowledge/_edit_result.html",
            error="Embedding service not configured. Set OPENAI_API_KEY to enable editing.",
        )

    # Optimistic concurrency check: verify entry hasn't been modified since form was loaded
    current_entry = None
    try:
        current_entry = service_client.get_entry(entry_id)
        if current_entry and form_version:
            try:
                if current_entry.version != int(form_version):
                    return render_template(
                        "knowledge/_edit_result.html",
                        error=(
                            "This entry was modified by another user "
                            f"(version {current_entry.version}). "
                            "Please reload the page and re-apply your changes."
                        ),
                    )
            except ValueError:
                pass  # Invalid version format, proceed without check
    except KBServiceError:
        pass  # If we can't check, proceed with the save attempt

    # Detect content changes to set validation_status="corrected"
    new_validation_status = None
    if current_entry:
        content_changed = title != (current_entry.title or "") or content != (
            current_entry.content or ""
        )
        if content_changed:
            new_validation_status = "corrected"

    try:
        new_version = service_client.update_entry(
            entry_id=entry_id,
            title=title,
            content=content,
            service=service,
            tags=tags,
            author="edit",
            embedding_service=embedding_service,
            validation_status=new_validation_status,
            entry_type=new_entry_type,
        )

        # Record edit diff in corrections collection when content changed
        if new_validation_status == "corrected" and current_entry:
            try:
                change_desc = _describe_edit_changes(
                    current_entry, title, content, tags, new_entry_type
                )
                correction = service_client.create_correction(
                    entry_id=entry_id,
                    user_message=f"Manual edit: {change_desc}",
                    assistant_response="Edit applied directly.",
                    summary=change_desc,
                )
                # Mark as applied immediately since edit is already saved
                service_client.update_correction(
                    correction_id=correction.correction_id,
                    status="applied",
                )
            except KBServiceError:
                # Don't fail the edit if correction recording fails
                logger.warning("Failed to record correction for edit on entry %s", entry_id)

        return render_template(
            "knowledge/_edit_result.html",
            success=True,
            entry_id=entry_id,
            title=title,
            new_version=new_version,
        )
    except KBServiceError as e:
        return render_template(
            "knowledge/_edit_result.html",
            error=str(e),
        )


def _describe_edit_changes(
    original: "KBEntry",
    new_title: str,
    new_content: str,
    new_tags: list[str],
    new_entry_type: str | None,
) -> str:
    """Generate a human-readable description of what changed in an edit.

    Args:
        original: The original KBEntry before editing
        new_title: The new title
        new_content: The new content
        new_tags: The new tags list
        new_entry_type: The new entry type (or None if unchanged)

    Returns:
        Description string of changes made.
    """
    changes: list[str] = []

    if new_title != (original.title or ""):
        changes.append("Title changed")

    old_content = original.content or ""
    if new_content != old_content:
        diff = len(new_content) - len(old_content)
        if diff > 0:
            changes.append(f"Content updated ({diff} chars added)")
        elif diff < 0:
            changes.append(f"Content updated ({abs(diff)} chars removed)")
        else:
            changes.append("Content updated")

    if sorted(new_tags) != sorted(original.tags or []):
        changes.append("Tags updated")

    if new_entry_type and new_entry_type != (original.entry_type or ""):
        changes.append(f"Category changed to {new_entry_type}")

    return "; ".join(changes) if changes else "Content modified"


@knowledge_bp.route("/preview", methods=["POST"])
def kb_preview() -> str:
    """Render markdown content for preview.

    Returns:
        Rendered HTML from the provided markdown content.
    """
    from beeper_ui.utils.markdown_utils import render_markdown

    content = request.form.get("content", "")
    return render_markdown(content)


# ── Confirmation route ──


@knowledge_bp.route("/<entry_id>/confirm", methods=["POST"])
def kb_confirm(entry_id: str) -> str:
    """Confirm an AI-generated KB entry as human-verified.

    Changes validation_status from 'AI-generated' to 'human-confirmed',
    versioned with the confirming user and timestamp.

    Args:
        entry_id: The unique identifier of the entry to confirm.

    Returns:
        Redirect to the entry detail page.
    """
    entry_id = sanitize_query(entry_id)
    user = request.form.get("user", "anonymous").strip() or "anonymous"
    service_client = get_kb_service()

    try:
        service_client.confirm_entry(entry_id, user)
        flash("Entry confirmed as human-verified", "success")
    except KBServiceError as e:
        flash(str(e), "error")

    return redirect(url_for("knowledge.kb_entry", entry_id=entry_id))


# ── Correction routes (must be before /<entry_id> catch-all) ──


@knowledge_bp.route("/<entry_id>/corrections/panel")
def kb_corrections_panel(entry_id: str) -> tuple[str, int] | str:
    """Load the correction panel for a KB entry.

    Args:
        entry_id: The KB entry to show corrections for

    Returns:
        Rendered correction panel partial or 404.
    """
    service_client = get_kb_service()

    try:
        entry = service_client.get_entry(entry_id)
    except KBServiceError as e:
        return render_template("knowledge/_correction_panel.html", error_message=str(e)), 500

    if not entry:
        return render_template(
            "knowledge/_correction_panel.html",
            error_message=f"Entry '{entry_id}' not found",
        ), 404

    return render_template(
        "knowledge/_correction_panel.html",
        entry=entry,
    )


@knowledge_bp.route("/<entry_id>/corrections", methods=["GET"])
def kb_corrections_history(entry_id: str) -> tuple[str, int] | str:
    """List corrections for a KB entry.

    Args:
        entry_id: The KB entry to list corrections for

    Returns:
        Rendered correction history partial or 404.
    """
    service_client = get_kb_service()

    try:
        entry = service_client.get_entry(entry_id)
    except KBServiceError as e:
        return render_template("knowledge/_correction_history.html", error_message=str(e)), 500

    if not entry:
        return render_template(
            "knowledge/_correction_history.html",
            error_message=f"Entry '{entry_id}' not found",
        ), 404

    try:
        corrections = service_client.get_corrections_for_entry(entry_id)
    except KBServiceError:
        corrections = []

    return render_template(
        "knowledge/_correction_history.html",
        entry=entry,
        corrections=corrections,
    )


@knowledge_bp.route("/<entry_id>/corrections", methods=["POST"])
def kb_submit_correction(entry_id: str) -> tuple[str, int] | str:
    """Submit a new correction for a KB entry.

    Args:
        entry_id: The KB entry to correct

    Returns:
        Rendered correction response partial or error.
    """
    service_client = get_kb_service()

    try:
        entry = service_client.get_entry(entry_id)
    except KBServiceError as e:
        return render_template("knowledge/_correction_response.html", error_message=str(e)), 500

    if not entry:
        return render_template(
            "knowledge/_correction_response.html",
            error_message=f"Entry '{entry_id}' not found",
        ), 404

    correction_text = sanitize_query(request.form.get("correction_text", ""))
    if not correction_text:
        return render_template(
            "knowledge/_correction_response.html",
            error_message="Correction text cannot be empty.",
        ), 400

    # Process correction via LLM
    try:
        corr_service = get_correction_service()
        result = corr_service.process_correction(
            entry_content=entry.content,
            entry_title=entry.title,
            correction_text=correction_text,
        )
    except CorrectionServiceError as e:
        return render_template(
            "knowledge/_correction_response.html",
            error_message=f"Unable to process correction: {e}",
        ), 503

    # Store correction in Qdrant
    try:
        correction = service_client.create_correction(
            entry_id=entry_id,
            user_message=correction_text,
            assistant_response=result["summary"],
            summary=result["summary"],
        )
    except KBServiceError as e:
        return render_template(
            "knowledge/_correction_response.html",
            error_message=f"Failed to save correction: {e}",
        ), 500

    return render_template(
        "knowledge/_correction_response.html",
        correction=correction,
        result=result,
        entry=entry,
    )


@knowledge_bp.route("/<entry_id>/corrections/<correction_id>/reply", methods=["POST"])
def kb_correction_reply(entry_id: str, correction_id: str) -> tuple[str, int] | str:
    """Submit a follow-up reply to a correction conversation.

    Args:
        entry_id: The KB entry being corrected
        correction_id: The correction conversation to reply to

    Returns:
        Rendered correction response partial or error.
    """
    service_client = get_kb_service()

    try:
        entry = service_client.get_entry(entry_id)
    except KBServiceError as e:
        return render_template("knowledge/_correction_response.html", error_message=str(e)), 500

    if not entry:
        return render_template(
            "knowledge/_correction_response.html",
            error_message=f"Entry '{entry_id}' not found",
        ), 404

    try:
        correction = service_client.get_correction(correction_id)
    except KBServiceError as e:
        return render_template("knowledge/_correction_response.html", error_message=str(e)), 500

    if not correction:
        return render_template(
            "knowledge/_correction_response.html",
            error_message=f"Correction '{correction_id}' not found",
        ), 404

    reply_text = sanitize_query(request.form.get("reply_text", ""))
    if not reply_text:
        return render_template(
            "knowledge/_correction_response.html",
            error_message="Reply text cannot be empty.",
        ), 400

    # Build conversation history from correction messages
    conversation_history = [
        {"role": msg.role, "content": msg.content} for msg in correction.messages
    ]

    # Process reply via LLM
    try:
        corr_service = get_correction_service()
        result = corr_service.process_reply(
            entry_content=entry.content,
            entry_title=entry.title,
            conversation_history=conversation_history,
            reply_text=reply_text,
        )
    except CorrectionServiceError as e:
        return render_template(
            "knowledge/_correction_response.html",
            error_message=f"Unable to process reply: {e}",
        ), 503

    # Add user message and assistant response to the correction
    try:
        service_client.add_correction_message(
            correction_id=correction_id,
            role="user",
            content=reply_text,
        )
        updated_correction = service_client.add_correction_message(
            correction_id=correction_id,
            role="assistant",
            content=result["summary"],
        )
    except KBServiceError as e:
        return render_template(
            "knowledge/_correction_response.html",
            error_message=f"Failed to save reply: {e}",
        ), 500

    return render_template(
        "knowledge/_correction_response.html",
        correction=updated_correction,
        result=result,
        entry=entry,
    )


@knowledge_bp.route("/<entry_id>/corrections/<correction_id>/revision", methods=["POST"])
def kb_generate_revision(entry_id: str, correction_id: str) -> tuple[str, int] | str:
    """Generate a revision of a KB entry based on a correction conversation.

    Args:
        entry_id: The KB entry to revise
        correction_id: The correction conversation to base revision on

    Returns:
        Rendered revision panel partial with diff, or error.
    """
    service_client = get_kb_service()

    try:
        entry = service_client.get_entry(entry_id)
    except KBServiceError as e:
        return render_template("knowledge/_revision_panel.html", error_message=str(e)), 500

    if not entry:
        return render_template(
            "knowledge/_revision_panel.html",
            error_message=f"Entry '{entry_id}' not found",
        ), 404

    try:
        correction = service_client.get_correction(correction_id)
    except KBServiceError as e:
        return render_template("knowledge/_revision_panel.html", error_message=str(e)), 500

    if not correction:
        return render_template(
            "knowledge/_revision_panel.html",
            error_message=f"Correction '{correction_id}' not found",
        ), 404

    if correction.entry_id != entry_id:
        return render_template(
            "knowledge/_revision_panel.html",
            error_message="Correction does not belong to this entry.",
        ), 400

    if correction.status != "pending":
        return render_template(
            "knowledge/_revision_panel.html",
            error_message=f"Correction is already '{correction.status}'.",
        ), 400

    # Build conversation messages
    conversation_messages = [
        {"role": msg.role, "content": msg.content} for msg in correction.messages
    ]

    # Generate revision via LLM
    try:
        corr_service = get_correction_service()
        revised_content = corr_service.generate_revision(
            entry_content=entry.content,
            entry_title=entry.title,
            correction_messages=conversation_messages,
        )
    except CorrectionServiceError as e:
        return render_template(
            "knowledge/_revision_panel.html",
            error_message=f"Unable to generate revision: {e}",
        ), 503

    # Generate diff
    diff_data = generate_diff(entry.content, revised_content)

    return render_template(
        "knowledge/_revision_panel.html",
        entry=entry,
        correction_id=correction_id,
        revised_content=revised_content,
        diff_data=diff_data,
    )


@knowledge_bp.route("/<entry_id>/corrections/<correction_id>/apply", methods=["POST"])
def kb_apply_revision(entry_id: str, correction_id: str) -> tuple[str, int] | str:
    """Apply a revision to a KB entry and mark correction as applied.

    Args:
        entry_id: The KB entry to update
        correction_id: The correction to mark as applied

    Returns:
        Rendered revision result partial, or error.
    """
    service_client = get_kb_service()

    try:
        entry = service_client.get_entry(entry_id)
    except KBServiceError as e:
        return render_template("knowledge/_revision_result.html", error_message=str(e)), 500

    if not entry:
        return render_template(
            "knowledge/_revision_result.html",
            error_message=f"Entry '{entry_id}' not found",
        ), 404

    try:
        correction = service_client.get_correction(correction_id)
    except KBServiceError as e:
        return render_template("knowledge/_revision_result.html", error_message=str(e)), 500

    if not correction:
        return render_template(
            "knowledge/_revision_result.html",
            error_message=f"Correction '{correction_id}' not found",
        ), 404

    if correction.entry_id != entry_id:
        return render_template(
            "knowledge/_revision_result.html",
            error_message="Correction does not belong to this entry.",
        ), 400

    if correction.status != "pending":
        return render_template(
            "knowledge/_revision_result.html",
            error_message=f"Correction is already '{correction.status}'.",
        ), 400

    revised_content = request.form.get("revised_content", "")
    if not revised_content:
        return render_template(
            "knowledge/_revision_result.html",
            error_message="No revised content provided.",
        ), 400

    # Apply the revision
    try:
        embedding_service = get_embedding_service()
        new_version = service_client.update_entry(
            entry_id=entry_id,
            content=revised_content,
            author="correction",
            embedding_service=embedding_service,
        )
    except KBServiceError as e:
        return render_template(
            "knowledge/_revision_result.html",
            error_message=f"Failed to apply revision: {e}",
        ), 500

    # Mark correction as applied
    try:
        service_client.update_correction(
            correction_id=correction_id,
            status="applied",
        )
    except KBServiceError:
        pass  # Non-critical; entry is already updated

    # Trigger learning analysis (non-blocking — failure doesn't affect apply)
    try:
        correction = service_client.get_correction(correction_id)
        if correction:
            learn_service = get_learning_service()
            conversation_messages = [
                {"role": msg.role, "content": msg.content} for msg in correction.messages
            ]
            service_name = entry.service or "general"
            learned_patterns = learn_service.analyze_correction(
                entry_content=entry.content,
                revised_content=revised_content,
                entry_title=entry.title,
                service_name=service_name,
                correction_messages=conversation_messages,
            )
            for pattern in learned_patterns:
                service_client.create_learning_pattern(
                    entry_id=entry_id,
                    correction_id=correction_id,
                    service_name=service_name,
                    category=pattern.get("category", "other"),
                    description=pattern.get("description", ""),
                    original_snippet=pattern.get("original_snippet", ""),
                    corrected_snippet=pattern.get("corrected_snippet", ""),
                )
    except (LearningServiceError, KBServiceError) as e:
        logger.warning(f"Learning analysis failed (non-blocking): {e}")
    except Exception as e:
        logger.warning(f"Unexpected learning error (non-blocking): {e}")

    # Re-evaluate trust for this service (non-blocking)
    try:
        service_name = entry.service or "general"
        service_client.evaluate_trust_graduation(service_name)
    except KBServiceError as e:
        logger.warning(f"Trust evaluation failed (non-blocking): {e}")
    except Exception as e:
        logger.warning(f"Unexpected trust error (non-blocking): {e}")

    return render_template(
        "knowledge/_revision_result.html",
        entry=entry,
        new_version=new_version,
        correction_id=correction_id,
    )


@knowledge_bp.route("/<entry_id>/corrections/<correction_id>/revision/refine", methods=["POST"])
def kb_refine_revision(entry_id: str, correction_id: str) -> tuple[str, int] | str:
    """Refine a previously generated revision based on user feedback.

    Args:
        entry_id: The KB entry being revised
        correction_id: The correction conversation

    Returns:
        Rendered revision panel partial with updated diff, or error.
    """
    service_client = get_kb_service()

    try:
        entry = service_client.get_entry(entry_id)
    except KBServiceError as e:
        return render_template("knowledge/_revision_panel.html", error_message=str(e)), 500

    if not entry:
        return render_template(
            "knowledge/_revision_panel.html",
            error_message=f"Entry '{entry_id}' not found",
        ), 404

    try:
        correction = service_client.get_correction(correction_id)
    except KBServiceError as e:
        return render_template("knowledge/_revision_panel.html", error_message=str(e)), 500

    if not correction:
        return render_template(
            "knowledge/_revision_panel.html",
            error_message=f"Correction '{correction_id}' not found",
        ), 404

    if correction.status != "pending":
        return render_template(
            "knowledge/_revision_panel.html",
            error_message=f"Correction is already '{correction.status}'.",
        ), 400

    feedback = request.form.get("feedback", "").strip()[:2000]
    if not feedback:
        return render_template(
            "knowledge/_revision_panel.html",
            error_message="Feedback text cannot be empty.",
        ), 400

    previous_revision = request.form.get("revised_content", "")
    if not previous_revision:
        return render_template(
            "knowledge/_revision_panel.html",
            error_message="No previous revision provided.",
        ), 400

    # Store feedback as correction message and reload for fresh messages
    try:
        updated_correction = service_client.add_correction_message(
            correction_id=correction_id,
            role="user",
            content=f"[Revision feedback] {feedback}",
        )
    except KBServiceError:
        updated_correction = None

    # Build conversation messages from updated correction (includes feedback history)
    source_messages = updated_correction.messages if updated_correction else correction.messages
    conversation_messages = [{"role": msg.role, "content": msg.content} for msg in source_messages]

    # Refine revision via LLM
    try:
        corr_service = get_correction_service()
        revised_content = corr_service.refine_revision(
            entry_content=entry.content,
            entry_title=entry.title,
            correction_messages=conversation_messages,
            previous_revision=previous_revision,
            feedback=feedback,
        )
    except CorrectionServiceError as e:
        return render_template(
            "knowledge/_revision_panel.html",
            error_message=f"Unable to refine revision: {e}",
        ), 503

    # Generate diff
    diff_data = generate_diff(entry.content, revised_content)

    return render_template(
        "knowledge/_revision_panel.html",
        entry=entry,
        correction_id=correction_id,
        revised_content=revised_content,
        diff_data=diff_data,
    )


@knowledge_bp.route("/learning")
def kb_learning() -> tuple[str, int] | str:
    """Display learning insights page with correction patterns and metrics.

    Returns:
        Rendered learning insights page.
    """
    service_client = get_kb_service()

    try:
        summary = service_client.get_learning_summary()
    except KBServiceError as e:
        return render_template(
            "knowledge/learning.html",
            summary={"total": 0, "by_category": {}, "by_service": {}, "patterns": []},
            error_message=str(e),
        )

    return render_template(
        "knowledge/learning.html",
        summary=summary,
        error_message=None,
    )


@knowledge_bp.route("/learning/adjustments")
def kb_learning_adjustments() -> tuple[str, int] | str:
    """Generate and return prompt adjustments based on accumulated patterns.

    Accepts optional ?service= query parameter to scope adjustments.

    Returns:
        Rendered adjustments partial.
    """
    service_name = request.args.get("service") or None
    service_client = get_kb_service()

    try:
        patterns = service_client.get_learning_patterns(service_name=service_name)
    except KBServiceError as e:
        return render_template(
            "knowledge/_learning_adjustments.html",
            adjustments=[],
            error_message=str(e),
        )

    if not patterns:
        return render_template(
            "knowledge/_learning_adjustments.html",
            adjustments=[],
            error_message=None,
        )

    pattern_dicts = [
        {
            "category": p.category,
            "description": p.description,
            "service_name": p.service_name,
        }
        for p in patterns
    ]

    try:
        learn_service = get_learning_service()
        adjustments = learn_service.generate_prompt_adjustments(pattern_dicts, service_name)
    except LearningServiceError as e:
        return render_template(
            "knowledge/_learning_adjustments.html",
            adjustments=[],
            error_message=f"Unable to generate adjustments: {e}",
        ), 503

    return render_template(
        "knowledge/_learning_adjustments.html",
        adjustments=adjustments,
        error_message=None,
    )


@knowledge_bp.route("/api/learning/prompt-context/<service_name>")
def kb_learning_prompt_context(service_name: str) -> tuple[dict[str, Any], int]:
    """Get prompt context for a service based on accumulated learning.

    This endpoint is designed for investigator integration — it returns
    a JSON object with prompt adjustments derived from past corrections.

    Args:
        service_name: Service to get prompt context for

    Returns:
        JSON response with prompt_context and adjustments.
    """
    service_client = get_kb_service()

    try:
        patterns = service_client.get_learning_patterns(service_name=service_name)
    except KBServiceError as e:
        logger.warning("Prompt context query failed: %s", e)
        return {
            "error": "Failed to retrieve learning patterns",
            "prompt_context": "",
            "adjustments": [],
        }, 500

    if not patterns:
        return {"prompt_context": "", "adjustments": [], "pattern_count": 0}, 200

    pattern_dicts = [
        {
            "category": p.category,
            "description": p.description,
            "service_name": p.service_name,
        }
        for p in patterns
    ]

    try:
        learn_service = get_learning_service()
        adjustments = learn_service.generate_prompt_adjustments(pattern_dicts, service_name)
        # Build context string from adjustments (avoids second LLM call)
        if adjustments:
            scope = f" for {service_name}" if service_name else ""
            context_lines = [f"Based on past corrections{scope}, keep these in mind:"]
            for adj in adjustments:
                context_lines.append(f"- {adj}")
            prompt_context = "\n".join(context_lines)
        else:
            prompt_context = ""
    except LearningServiceError:
        return {
            "error": "Unable to generate prompt context",
            "prompt_context": "",
            "adjustments": [],
        }, 503

    return {
        "prompt_context": prompt_context,
        "adjustments": adjustments,
        "pattern_count": len(patterns),
    }, 200


@knowledge_bp.route("/trust-settings")
def kb_trust_settings() -> tuple[str, int] | str:
    """Display trust settings page with per-service trust levels.

    Returns:
        Rendered trust settings page.
    """
    service_client = get_kb_service()

    try:
        trusts = service_client.get_all_service_trusts()
    except KBServiceError as e:
        logger.warning("Trust settings query failed: %s", e)
        return render_template(
            "knowledge/trust_settings.html",
            trusts=[],
            error_message="Unable to load trust data",
        )

    return render_template(
        "knowledge/trust_settings.html",
        trusts=trusts,
        error_message=None,
    )


@knowledge_bp.route("/trust-settings/<service_name>/override", methods=["POST"])
def kb_trust_override(
    service_name: str,
) -> tuple[str, int] | str:
    """Manually override a service's trust level.

    Args:
        service_name: Service to override trust for

    Returns:
        Rendered override result partial.
    """
    # Validate service_name (alphanumeric, hyphens, underscores, max 100)
    if (
        not service_name
        or len(service_name) > 100
        or not re.match(r"^[a-zA-Z0-9_-]+$", service_name)
    ):
        return render_template(
            "knowledge/_trust_override_result.html",
            error_message="Invalid service name",
        ), 400

    trust_level = request.form.get("trust_level", "draft")
    reason = request.form.get("reason", "")

    if trust_level not in ("draft", "trusted"):
        return render_template(
            "knowledge/_trust_override_result.html",
            error_message="Invalid trust level",
        ), 400

    if not reason or not reason.strip():
        return render_template(
            "knowledge/_trust_override_result.html",
            error_message="Reason is required for manual override",
        ), 400

    reason = reason.strip()[:500]

    service_client = get_kb_service()

    try:
        trust = service_client.set_manual_trust_override(
            service_name=service_name,
            trust_level=trust_level,
            reason=reason,
        )
    except KBServiceError as e:
        logger.warning("Trust override failed for %s: %s", service_name, e)
        return render_template(
            "knowledge/_trust_override_result.html",
            error_message="Failed to update trust level",
        ), 500

    return render_template(
        "knowledge/_trust_override_result.html",
        trust=trust,
        error_message=None,
    )


@knowledge_bp.route("/services/<service_name>/knowledge")
def service_knowledge(service_name: str) -> tuple[str, int] | str:
    """Display per-service knowledge view with entries grouped by category.

    Args:
        service_name: The service name to view knowledge for.

    Returns:
        Rendered service knowledge page or 404 if service unknown.
    """
    service_client = get_kb_service()

    # Sanitize input
    clean_name = sanitize_query(service_name)
    if not clean_name:
        return render_template(
            "knowledge/service_knowledge.html",
            service_name="",
            groups={"root_causes": [], "runbooks": [], "proven_fixes": [], "patterns": []},
            validation_counts={"total": 0},
            active_filter=None,
            available_services=[],
            error_message="Invalid service name",
        ), 404

    # Verify service exists
    try:
        available_services = service_client.get_available_services()
    except KBServiceError:
        available_services = []

    if clean_name not in available_services:
        return render_template(
            "knowledge/service_knowledge.html",
            service_name=clean_name,
            groups={"root_causes": [], "runbooks": [], "proven_fixes": [], "patterns": []},
            validation_counts={"total": 0},
            active_filter=None,
            available_services=available_services,
            error_message=f"Service '{clean_name}' not found in knowledge base",
        ), 404

    # Get validation status filter
    validation_status = request.args.get("validation_status")
    if validation_status and validation_status not in VALID_VALIDATION_STATUSES:
        validation_status = None

    try:
        groups = service_client.get_service_knowledge_grouped(
            service_name=clean_name,
            validation_status=validation_status,
        )
        validation_counts = service_client.get_service_validation_counts(clean_name)
    except KBServiceError as e:
        logger.error(f"Failed to load service knowledge for {clean_name}: {e}")
        return render_template(
            "knowledge/service_knowledge.html",
            service_name=clean_name,
            groups={"root_causes": [], "runbooks": [], "proven_fixes": [], "patterns": []},
            validation_counts={"total": 0},
            active_filter=None,
            available_services=available_services,
            error_message="Failed to load knowledge entries. Please try again later.",
        )

    return render_template(
        "knowledge/service_knowledge.html",
        service_name=clean_name,
        groups=groups,
        validation_counts=validation_counts,
        active_filter=validation_status,
        available_services=available_services,
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
    source_investigation: dict[str, str] | None = None
    contributing_investigations: list[dict[str, str]] = []

    try:
        entry = service_client.get_entry(entry_id)
        if entry:
            related_entries = service_client.list_related_entries(
                entry_id=entry_id, service=entry.service, limit=5
            )
            # Fetch payload once for both link methods (avoids 2 extra Qdrant queries)
            entry_payload = service_client.get_entry_payload(entry_id)
            source_investigation = service_client.get_source_investigation(
                entry_id, payload=entry_payload
            )
            contributing_investigations = service_client.get_contributing_investigations(
                entry_id, payload=entry_payload
            )
    except KBServiceError as e:
        error_message = str(e)

    if not entry and not error_message:
        return (
            render_template(
                "knowledge/entry.html",
                entry=None,
                related_entries=[],
                source_investigation=None,
                contributing_investigations=[],
                error_message=f"Entry '{entry_id}' not found",
            ),
            404,
        )

    return render_template(
        "knowledge/entry.html",
        entry=entry,
        related_entries=related_entries,
        source_investigation=source_investigation,
        contributing_investigations=contributing_investigations,
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


# ---------------------------------------------------------------------------
# JSON API (Task 5.1) — /api/v1/knowledge/*
#
# Consumed by the React KB browse/search + entry-detail views
# (`docs/design/route-parity-targets.md` §2: `/app/knowledge`,
# `/app/knowledge/:entryId`). These handlers are thin JSON adapters over the
# exact same `KBService`/`EmbeddingService` calls `kb_index()`/`kb_search()`/
# `kb_entry()` above already make — no KB logic is reimplemented here, and
# none of the existing Jinja routes' behavior changes.
# ---------------------------------------------------------------------------

# Preview/snippet length for list & search results — mirrors the Jinja
# `_entry_card.html` (`preview[:200]`) / `_search_results.html`
# (`truncate(200)`) 200-char convention.
SNIPPET_LENGTH = 200


def _snippet(content: str | None) -> str:
    """Plain-text preview of markdown content, truncated to SNIPPET_LENGTH."""
    plain = strip_markdown(content or "")
    if len(plain) > SNIPPET_LENGTH:
        return plain[:SNIPPET_LENGTH] + "…"
    return plain


def _kb_entry_summary(entry: "KBEntry") -> dict[str, Any]:
    """Serialize a KBEntry for list/search/related-entries JSON responses."""
    return {
        "id": entry.id,
        "entry_id": entry.entry_id,
        "entry_type": entry.entry_type,
        "title": entry.title,
        "service": entry.service,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
        "author": entry.author,
        "version": entry.version,
        "tags": entry.tags,
        "validation_status": entry.validation_status,
        "auto_published": entry.auto_published,
        "relevance_score": entry.relevance_score,
        "snippet": _snippet(entry.content),
    }


def _kb_entry_detail(entry: "KBEntry") -> dict[str, Any]:
    """Serialize a KBEntry for the entry-detail JSON response (FR31).

    `content_html` reuses the existing sanitized markdown renderer
    (`render_markdown`, the same function the Jinja `entry.content|markdown`
    filter calls) so the React view never needs its own markdown
    parser/sanitizer — the server stays the single source of sanitization.
    `root_cause`/`resolution`/`affected_services` are the FR31 structured
    incident-detail fields `KBEntry` already carries (with the markdown
    content remaining the source-of-truth fallback) — reused verbatim, not
    re-derived.
    """
    summary = _kb_entry_summary(entry)
    del summary["snippet"]
    return {
        **summary,
        "content_html": render_markdown(entry.content or ""),
        "root_cause": entry.root_cause,
        "resolution": entry.resolution,
        "affected_services": entry.affected_services,
    }


@knowledge_api_bp.route("/")
@require_role("user")
def knowledge_list_json() -> tuple[Response, int] | Response:
    """JSON browse/search endpoint for the React KB view (Task 5.1, FR28/FR29).

    Query parameters mirror `kb_index()`/`kb_search()` above exactly:
    - q: search query (optional). When present, performs the same semantic
      search `kb_search()` uses (`KBService.search_semantic` +
      `EmbeddingService`); when absent, browses recent entries
      (`KBService.list_recent_entries()`), matching `kb_index()`.
    - entry_type, service, date_range: optional filters, same validation as
      the Jinja routes. Not required by FR53 (only `q` is) — supported here
      so a future filter UI can adopt them without a backend change.

    Response shape:
        { "query": str, "entries": [...], "has_exact_matches": bool, "error": str | null }

    A soft/expected condition (search not configured — no OPENAI_API_KEY) or
    a per-entry_type/service scan failure returns 200 with a populated
    `error` string (matching the Jinja route's graceful degrade, which
    renders inline rather than failing the page). An operator/Qdrant
    connection failure (`KBServiceError`) returns 503, matching
    `investigations_api_bp`'s convention in `investigations.py`.
    """
    query = sanitize_query(request.args.get("q", ""))
    entry_type = validate_entry_type(request.args.get("entry_type"))
    service = request.args.get("service") or None
    date_range = request.args.get("date_range") or None
    date_from, date_to = parse_date_range(date_range or "")

    service_client = get_kb_service()

    if query:
        embedding_service = get_embedding_service()
        if not embedding_service.is_configured():
            return jsonify(
                {
                    "query": query,
                    "entries": [],
                    "has_exact_matches": True,
                    "error": "Search not configured. Set OPENAI_API_KEY to enable.",
                }
            )
        try:
            entries, has_exact_matches = service_client.search_semantic(
                query=query,
                limit=10,
                entry_type=entry_type,
                service=service,
                date_from=date_from,
                date_to=date_to,
                embedding_service=embedding_service,
            )
        except KBServiceError as e:
            return jsonify(
                {"query": query, "entries": [], "has_exact_matches": True, "error": str(e)}
            ), 503
    else:
        try:
            entries = service_client.list_recent_entries(
                limit=20,
                entry_type=entry_type,
                service=service,
                date_from=date_from,
                date_to=date_to,
            )
        except KBServiceError as e:
            return jsonify(
                {"query": query, "entries": [], "has_exact_matches": True, "error": str(e)}
            ), 503
        has_exact_matches = True

    return jsonify(
        {
            "query": query,
            "entries": [_kb_entry_summary(e) for e in entries],
            "has_exact_matches": has_exact_matches,
            "error": None,
        }
    )


@knowledge_api_bp.route("/<entry_id>")
@require_role("user")
def knowledge_entry_json(entry_id: str) -> tuple[Response, int] | Response:
    """JSON entry-detail endpoint for the React KB entry view (Task 5.1, FR31).

    Mirrors `kb_entry()` above: fetches the entry, its related entries
    (same-service, `list_related_entries`), and its bi-directional
    investigation links (`get_source_investigation`/
    `get_contributing_investigations`), reusing the exact same `KBService`
    calls. Missing entry returns 404 with `{"error": "not_found"}`
    (matching `investigation_detail_json`'s convention in
    `investigations.py`); a Qdrant/service failure returns 503.
    """
    service_client = get_kb_service()

    try:
        entry = service_client.get_entry(entry_id)
    except KBServiceError as e:
        return jsonify({"error": str(e)}), 503

    if not entry:
        return jsonify({"error": "not_found"}), 404

    try:
        related_entries = service_client.list_related_entries(
            entry_id=entry_id, service=entry.service, limit=5
        )
    except KBServiceError:
        related_entries = []

    source_investigation: dict[str, str] | None = None
    contributing_investigations: list[dict[str, str]] = []
    try:
        entry_payload = service_client.get_entry_payload(entry_id)
        source_investigation = service_client.get_source_investigation(
            entry_id, payload=entry_payload
        )
        contributing_investigations = service_client.get_contributing_investigations(
            entry_id, payload=entry_payload
        )
    except KBServiceError:
        pass  # Non-critical — entry-detail links degrade gracefully, matching kb_entry().

    return jsonify(
        {
            "entry": _kb_entry_detail(entry),
            "related_entries": [_kb_entry_summary(e) for e in related_entries],
            "source_investigation": source_investigation,
            "contributing_investigations": contributing_investigations,
        }
    )
