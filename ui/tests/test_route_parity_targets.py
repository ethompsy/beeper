"""Tests for Task 5.0: route parity-target inventory guard.

Acceptance criterion [T] (docs/plans/react-ui.md, Milestone 2.1):
  "Each migrated route has a written parity target (FR id or
  `templates/<name>.html`) before its task starts — no 'parity with what?'
  gaps."

This is a pure-parse guard, not a Flask-app or React test: it reads the
parity-target document (`docs/design/route-parity-targets.md`), the sidebar
nav declaration (`ui/beeper_ui/templates/components/layout.html`), and the
requirements doc (`docs/reqs/main.md`), and asserts they are mutually
consistent:

  1. Every sidebar nav destination declared in `layout.html` (16 as of this
     writing) is covered by the parity-target doc — its Jinja URL appears
     verbatim in either a per-task `- **Jinja URL(s):**` field (Tasks
     5.1-5.4 + the already-migrated Investigations surface) or in the §7
     "later increment, target pinned" table's Jinja URL column. A future nav
     addition that isn't added to the doc fails this test instead of
     silently going untracked.
  2. Every per-task route block's `- **Parity target:**` field (6 blocks:
     Investigations, KB, Ingestion Stats, Sources, Spending, Metrics) is
     non-empty
     and resolves to at least one of: a `templates/<name>.html` path that
     actually exists on disk under `ui/beeper_ui/templates/`, or a
     well-formed `FR<n>` id that is actually defined in `docs/reqs/main.md`
     (as a `- FR<n>:` line) — never an invented id or a dangling path.
  3. Every §7 "later increment" table row's Parity target column passes the
     same resolve-to-a-real-target check.
  4. Task 5.4 (Metrics) specifically pins `templates/metrics/mttr.html` with
     no invented FR id — the exact gap Task 5.0 exists to close.

No Flask app is constructed and no frontend build is required; this suite
only depends on the repo's own doc/template files being present, so it runs
unconditionally in the "Python UI" CI job.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).parent
_UI_DIR = _TESTS_DIR.parent
_REPO_ROOT = _UI_DIR.parent

_DOC_PATH = _REPO_ROOT / "docs" / "design" / "route-parity-targets.md"
_LAYOUT_PATH = _UI_DIR / "beeper_ui" / "templates" / "components" / "layout.html"
_TEMPLATES_DIR = _UI_DIR / "beeper_ui" / "templates"
_REQS_PATH = _REPO_ROOT / "docs" / "reqs" / "main.md"

# The doc's "## 1. Already migrated" heading marks the start of the actual
# route inventory content; everything before it is the "how to read a route
# block" explanatory preamble, whose field examples (e.g. a literal
# `templates/<name>.html` placeholder) must NOT be parsed as real citations.
_CONTENT_START_MARKER = "## 1. Already migrated"
_SECTION7_HEADER = (
    "| Nav label | Group | Jinja URL(s) | Dual-mode/HTMX | Parity target | Data source |"
)

_NAV_ITEM_RE = re.compile(r"\{'label': '([^']+)', 'url': '([^']+)'\}")
_JINJA_URL_BULLET_RE = re.compile(r"^- \*\*Jinja URL\(s\):\*\* (.+)$", re.MULTILINE)
# Task 6.3: once a Jinja URL is retired, `layout.html`'s sidebar links
# straight at its React URL instead (see that macro's own comments) — the
# nav-coverage check below must also recognize this bullet as "documented".
_REACT_URL_BULLET_RE = re.compile(
    r"^- \*\*React URL \(canonical, dev-time, under `/app`\):\*\* (.+)$", re.MULTILINE
)
_PARITY_TARGET_BULLET_RE = re.compile(r"^- \*\*Parity target:\*\* (.+)$", re.MULTILINE)
# Task 6.3 (D13/D14): marks a per-task parity-target bullet whose cited
# Jinja template(s) were deliberately deleted — the resolution check for a
# retired bullet flips (the template must NOT exist on disk) rather than
# failing outright. Always immediately follows its `Parity target` bullet
# (see route-parity-targets.md §1-§5) — matched positionally in
# `_is_retired_bullet()` below, not embedded in the bullet text itself, so
# `_PARITY_TARGET_BULLET_RE`'s capture stays exactly what it always was.
_RETIRED_MARKER_RE = re.compile(r"^- \*\*RETIRED \(Task 6\.3", re.MULTILINE)
_BACKTICK_URL_RE = re.compile(r"`(/[^`\s]*)`")
_TEMPLATE_PATH_RE = re.compile(r"`templates/([^`]+\.html)`")
_FR_ID_RE = re.compile(r"\bFR\d+\b")


def _doc_text() -> str:
    assert _DOC_PATH.is_file(), f"parity-target doc not found: {_DOC_PATH}"
    return _DOC_PATH.read_text()


def _doc_body() -> str:
    """The doc's content from '## 1. Already migrated' onward (excludes the preamble)."""
    text = _doc_text()
    idx = text.index(_CONTENT_START_MARKER)
    return text[idx:]


def _nav_items() -> list[tuple[str, str]]:
    """Parse (label, url) pairs out of the sidebar_group() calls in layout.html."""
    text = _LAYOUT_PATH.read_text()
    items = _NAV_ITEM_RE.findall(text)
    assert items, (
        "no {'label': ..., 'url': ...} nav items parsed from layout.html — "
        "the sidebar markup or this test's regex has drifted"
    )
    return items


def _valid_fr_ids() -> set[str]:
    text = _REQS_PATH.read_text()
    ids = set(re.findall(r"^- (FR\d+):", text, flags=re.MULTILINE))
    assert ids, "no '- FRn:' requirement lines parsed from docs/reqs/main.md"
    return ids


def _section7_rows() -> list[list[str]]:
    """Return the cell lists for each data row of the §7 later-increment table."""
    text = _doc_text()
    assert _SECTION7_HEADER in text, "§7 table header not found or has drifted"
    start = text.index(_SECTION7_HEADER)
    lines = text[start:].splitlines()
    rows: list[list[str]] = []
    # lines[0] is the header row, lines[1] is the '|---|---|...' separator.
    for line in lines[2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    return rows


def _is_retired_bullet(body: str, bullet_end: int) -> bool:
    """True if a `- **RETIRED (Task 6.3` marker immediately follows the
    parity-target bullet ending at `bullet_end` (the next non-blank line)."""
    rest = body[bullet_end:].lstrip("\n")
    return rest.startswith("- **RETIRED (Task 6.3")


def _target_resolves(
    target_text: str, valid_fr_ids: set[str], retired: bool = False
) -> tuple[bool, list[str]]:
    """Check a parity-target citation string against real templates/FR ids.

    Returns (resolves, problems) — resolves is True iff at least one cited
    template path exists on disk or at least one cited FR id is defined in
    docs/reqs/main.md; problems lists every individual citation that failed
    to resolve (a target can legitimately cite several ids/paths).

    `retired=True` (Task 6.3) flips the template half of this check: the
    route's Jinja render path was deliberately removed, so the cited
    template(s) must NOT exist on disk — proving the retirement actually
    happened, not just that it was documented. FR ids (where present, e.g.
    Investigations/KB/Ingestion Stats/Sources/Spending) are untouched by
    retirement — they still describe the feature the React view now
    provides — so their validity is still checked normally.
    """
    problems: list[str] = []

    template_paths = _TEMPLATE_PATH_RE.findall(target_text)
    if retired:
        for rel in template_paths:
            if (_TEMPLATES_DIR / rel).is_file():
                problems.append(
                    f"marked RETIRED (Task 6.3) but template still exists on disk: "
                    f"templates/{rel}"
                )
        resolved_templates = [] if problems else template_paths
    else:
        resolved_templates = []
        for rel in template_paths:
            full = _TEMPLATES_DIR / rel
            if full.is_file():
                resolved_templates.append(rel)
            else:
                problems.append(f"template not found on disk: templates/{rel}")

    fr_ids = _FR_ID_RE.findall(target_text)
    resolved_frs = []
    for fr in fr_ids:
        if fr in valid_fr_ids:
            resolved_frs.append(fr)
        else:
            problems.append(f"FR id not defined in docs/reqs/main.md: {fr}")

    if retired:
        # A retired bullet resolves iff every cited template is confirmed
        # gone AND every cited FR id (if any) is still valid — `problems`
        # already accumulated both failure kinds above.
        resolves = not problems
    else:
        resolves = bool(resolved_templates) or bool(resolved_frs)
        if not resolves:
            problems.append(
                f"no resolvable template path or FR id found in parity target text: "
                f"{target_text!r}"
            )
    return resolves, problems


# ── fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def valid_fr_ids() -> set[str]:
    return _valid_fr_ids()


# ── AC: doc exists and covers every sidebar nav destination ───────────────


class TestNavCoverage:
    def test_doc_file_exists(self) -> None:
        assert _DOC_PATH.is_file(), f"expected the Task 5.0 parity-target doc at {_DOC_PATH}"

    def test_sixteen_nav_items_parsed_from_layout(self) -> None:
        # Sanity check that this test's regex still matches the live sidebar
        # markup and the inventory hasn't silently grown/shrunk unnoticed.
        assert len(_nav_items()) == 16

    def test_every_sidebar_nav_destination_has_a_doc_entry(self) -> None:
        nav_items = _nav_items()
        body = _doc_body()

        covered_urls: set[str] = set()
        for bullet in _JINJA_URL_BULLET_RE.findall(body):
            covered_urls.update(_BACKTICK_URL_RE.findall(bullet))
        # Task 6.3: a retired route's sidebar link now points at its React
        # URL, not its (redirecting) bare Jinja URL — also accept a nav
        # item covered via the doc's own "React URL" bullet, which every
        # per-task block has always carried.
        for bullet in _REACT_URL_BULLET_RE.findall(body):
            covered_urls.update(_BACKTICK_URL_RE.findall(bullet))
        for row in _section7_rows():
            if len(row) > 2:  # column 2 = "Jinja URL(s)"
                covered_urls.update(_BACKTICK_URL_RE.findall(row[2]))

        missing = [(label, url) for label, url in nav_items if url not in covered_urls]
        assert not missing, (
            "Sidebar nav destinations with no parity-target entry in "
            f"docs/design/route-parity-targets.md: {missing}. Every nav item "
            "in layout.html must appear as a backtick-quoted URL in either a "
            "'- **Jinja URL(s):**' field, a '- **React URL...**' field, or "
            "the §7 table's Jinja URL column."
        )


# ── AC: every migrated-route parity target resolves to a real target ──────


class TestParityTargetsResolve:
    def test_six_per_task_parity_target_bullets_present(self) -> None:
        # §1 (Investigations, shipped) + 5.1 (KB) + 5.2 (Ingestion Stats) +
        # 5.3a (Sources) + 5.3b (Spending) + 5.4 (Metrics) = 6 blocks with
        # exactly one '- **Parity target:**' field apiece.
        bullets = _PARITY_TARGET_BULLET_RE.findall(_doc_body())
        assert len(bullets) == 6, (
            f"expected 6 per-task '- **Parity target:**' bullets (§1-§5), "
            f"found {len(bullets)}: {bullets}"
        )

    def test_each_task_block_parity_target_resolves(self, valid_fr_ids: set[str]) -> None:
        body = _doc_body()
        failures = []
        for match in _PARITY_TARGET_BULLET_RE.finditer(body):
            bullet = match.group(1)
            retired = _is_retired_bullet(body, match.end())
            ok, problems = _target_resolves(bullet, valid_fr_ids, retired=retired)
            if not ok:
                failures.append({"target": bullet, "retired": retired, "problems": problems})
        assert not failures, f"unresolved per-task parity targets: {failures}"

    def test_all_six_per_task_bullets_are_retired_by_task_6_3(self) -> None:
        # Every Milestone-2.1 migrated route (§1-§5) was retired by Task 6.3
        # — guards against a bullet's RETIRED marker silently going missing
        # (or being added to the wrong line) on a future doc edit.
        body = _doc_body()
        retired_count = sum(
            1
            for match in _PARITY_TARGET_BULLET_RE.finditer(body)
            if _is_retired_bullet(body, match.end())
        )
        assert retired_count == 6

    def test_section7_table_has_ten_later_increment_rows(self) -> None:
        # 16 nav items - 1 shipped (Investigations) - 5 Task 5.1-5.4 targets
        # (KB, Ingestion Stats, Sources, Spending, Metrics) = 10 remaining.
        rows = _section7_rows()
        assert len(rows) == 10, (
            f"expected 10 'later increment' rows in the §7 table, found {len(rows)}: {rows}"
        )

    def test_section7_table_parity_targets_resolve(self, valid_fr_ids: set[str]) -> None:
        failures = []
        for row in _section7_rows():
            label = row[0] if row else "<unparsed row>"
            parity_cell = row[4] if len(row) > 4 else ""
            ok, problems = _target_resolves(parity_cell, valid_fr_ids)
            if not ok:
                failures.append({"nav_label": label, "target": parity_cell, "problems": problems})
        assert not failures, f"unresolved parity targets in the §7 table: {failures}"


# ── AC: Task 5.4's explicit "parity with what?" gap is closed ─────────────


class TestMetricsTask54ParityTarget:
    """The Metrics view is the task description's named 'parity with what?'
    gap. Locks the resolution in place so a future doc edit can't silently
    reopen it by inventing an FR id or dropping the template citation.

    Task 6.3 (D13/D14) subsequently retired `metrics/mttr.html` itself
    (`/metrics/*` now redirects to `/app/metrics`) — the citation stays in
    the doc as a historical record of what "parity" meant, but the file it
    names is now gone by design; see `TestParityTargetsResolve` above for
    the general retired-bullet handling this class's first test also checks.
    """

    def _task_5_4_section(self) -> str:
        text = _doc_text()
        start = text.index("## 5. Task 5.4")
        end = text.index("## 6. Known parity gaps")
        return text[start:end]

    def _task_5_4_parity_target_text(self) -> str:
        match = _PARITY_TARGET_BULLET_RE.search(self._task_5_4_section())
        assert match is not None, "Task 5.4 section has no '- **Parity target:**' bullet"
        return match.group(1)

    def test_metrics_parity_target_still_names_the_mttr_template(self) -> None:
        # The citation is retained as a historical record even though the
        # file no longer exists (see the next test).
        target = self._task_5_4_parity_target_text()
        assert "templates/metrics/mttr.html" in target

    def test_metrics_parity_target_is_marked_retired_and_template_is_gone(self) -> None:
        section = self._task_5_4_section()
        match = _PARITY_TARGET_BULLET_RE.search(section)
        assert match is not None
        assert _is_retired_bullet(section, match.end()), (
            "Task 5.4's parity target must carry a '- **RETIRED (Task 6.3...' "
            "marker immediately after it (Task 6.3 removed the template)"
        )
        assert not (_TEMPLATES_DIR / "metrics" / "mttr.html").is_file(), (
            "templates/metrics/mttr.html still exists on disk but Task 5.4's "
            "parity target is marked RETIRED — retirement was documented but "
            "not actually done"
        )

    def test_metrics_parity_target_does_not_invent_an_fr_id(self) -> None:
        target = self._task_5_4_parity_target_text()
        found = _FR_ID_RE.findall(target)
        assert not found, (
            "Task 5.4's parity target must not cite an FR id (no FR covers "
            f"the MTTR dashboard) — found: {found}"
        )
