# Beeper UI — Design Handoff

**Audience:** Claude Design (UI/UX detail, clarity, and polish pass)
**Owner:** e.thompsy@gmail.com
**Branch for this work:** `claude/handoff-design-lknw65`
**Status:** Open for full review & revision

---

## 1. What you're being handed

The complete **Beeper web UI** — a server-rendered Flask + HTMX + Tailwind v4
application (~112 Jinja templates across 15 feature areas). Beeper is an
**agentic SRE platform**: it watches production observability signals, auto-runs
investigations on anomalies, proposes root-cause hypotheses and remediations,
and learns from operator feedback via a knowledge base.

Your job is a **full UI/UX review and revision** — not a cosmetic skin. The
priorities, in order:

1. **Clarity & legibility for a working SRE.** This is the #1 ask. Today many
   features are hard to understand, and many labels are written in
   *internal/model-centric* language rather than in terms an on-call engineer
   would recognize. Make every screen answer "what is this, why do I care, what
   do I do next?"
2. **Information architecture & labeling.** Re-name, re-group, and re-explain
   features so the navigation and page titles map to SRE mental models, not to
   Beeper's internal subsystems.
3. **Visual consistency.** Spacing, typography, color/token usage, alignment,
   component reuse across all templates.
4. **States & feedback.** Empty, loading, error, and success states; HTMX swap
   transitions; micro-interactions.
5. **Accessibility.** Contrast (it's a dark theme), focus order, keyboard nav,
   ARIA, screen-reader labels.
6. **Responsive layout.** Breakpoints, the collapsing sidebar rail, and the
   command palette on small screens.

---

## 2. The clarity problem — concrete examples to fix

The current left-nav (grouped **Observe / Learn / Manage**) uses several labels
that a new SRE would not understand without reading the source. These are
representative, not exhaustive — assume the same problem exists inside pages:

| Current label / term | Why it's unclear | Direction (yours to refine) |
|---|---|---|
| **Trust** | "Trust" of what? It's the autonomy/confidence config for auto-remediation. | e.g. "Automation Settings" / "Autonomy & Approvals" |
| **Confidence Gates** | Internal mechanism name. | Frame around "when Beeper acts on its own vs. asks you." |
| **Handoff** | Ambiguous. It's the shift-change summary for on-call handover. | e.g. "Shift Handoff" / "On-call Handover." |
| **Ingestion Stats** | Pipeline-internal. | Frame as "Signal intake / data freshness." |
| **Sources** | OK-ish, but unclear vs. "Health." | Clarify: connected observability backends. |
| **Cost Insights** vs **Spending** | Two nav items, overlapping meaning. | Consolidate / disambiguate (LLM spend vs. budgets). |
| **Adaptive Threshold / Noise Report** | Detection-engine jargon surfaced raw to users. | Explain in outcome terms ("fewer false alarms"). |

**Method:** for each feature, read the intent in the spec + implementation
artifacts (Section 7), then propose user-facing language and surface it in a
glossary so terms stay consistent across screens.

---

## 3. How to see it running (your sandbox)

You do **not** need Kubernetes. The repo ships a standalone preview that runs
the full UI with realistic mock data:

```bash
cd ui
poetry install
make -C .. tailwind-build      # or: cd ui && tailwindcss --minify -i beeper_ui/static/css/input.css -o beeper_ui/static/css/tailwind.css
python demo_ui.py              # serves http://localhost:5050/investigations/
```

- `ui/demo_ui.py` patches the backend services with demo investigations/KB data,
  so every screen renders without infra. Start here for screenshots and iteration.
- `tailwind.css` is **gitignored** and must be built before the UI looks right.
  Run `make tailwind-watch` while iterating so CSS rebuilds on save.
- The full demo (live operator backend, real data) is `make demo-up` then
  `make demo-ui` → Beeper UI at `http://localhost:5050`. Only needed for
  end-to-end behavior; the mock preview is enough for design work.

---

## 4. Tech stack & hard constraints (the must-not-break list)

Server-rendered, **not** a SPA. "Polish" means Jinja templates + CSS, not a
component-library rewrite.

- **Flask** blueprints in `ui/beeper_ui/routes/`, **Jinja2** templates in
  `ui/beeper_ui/templates/`, **HTMX** for partial updates + **SSE** for live
  investigation updates. Partials are the `_underscore.html` files; they're
  swapped into full pages over the wire.
- **Tailwind CSS v4**, configured in `ui/beeper_ui/static/css/input.css`.
  Read the comments there before touching CSS — three non-obvious constraints:
  1. **Preflight (CSS reset) is DISABLED on purpose** to avoid breaking the
     legacy hand-written CSS. Only a minimal `<button>` reset is kept.
  2. **`main.css` is ~7,000 lines of load-bearing legacy CSS.** It defines
     unscoped element rules (`nav { display:flex }`, `header { padding… }`,
     `main { padding… }`) that fight Tailwind utilities. Prefer adding/adjusting
     tokens and utility classes; be very cautious editing `main.css`.
  3. **Tailwind utilities are imported UNLAYERED** so they win on normal
     specificity against those legacy element selectors. Don't re-layer them.
- **Breakpoints are custom** (`sm: 768px`, `lg: 1200px`, `xl: 1920px`); default
  Tailwind breakpoints are cleared. Use these, not `md`/`2xl`.

If a change risks the legacy CSS interaction, prefer a token/utility solution and
call it out in the PR.

---

## 5. Design system (current state)

**Design tokens v0.2.0** live in `ui/beeper_ui/static/css/input.css` (`@theme`):

```
Surfaces:  surface-base #0f0f1a · surface-raised #1a1a2e · surface-overlay #252540
Primary:   primary #6366f1 · primary-hover #818cf8
Status:    healthy #22c55e · warning #f59e0b · critical #ef4444 · muted #6b7280
Text:      text-primary #f8fafc · text-secondary #94a3b8 · text-muted #64748b
```

Dark theme by default. **Validate WCAG contrast** — `text-muted` on
`surface-base` is a likely failure; audit as part of the a11y pass.

**Existing UX spec (read this first):**
- `docs/specs/ux-design-specification.md` — canonical, 1,759 lines (IA,
  components, the Observe/Learn/Manage model, sidebar/command-palette patterns).
- `_bmad-output/planning-artifacts/ux-design-specification-v0.2.0.md` — earlier
  v0.2.0 cut; `ux-design-directions.html` has visual direction explorations.

Treat the spec as **context, not gospel** — the whole point of this handoff is
that the *as-built* UI drifted from clarity goals. Where the spec and the running
UI disagree with good UX, propose the better answer and note the deviation.

---

## 6. Information architecture (current nav → routes)

| Group | Item (current label) | Route |
|---|---|---|
| **Observe** | Investigations | `/investigations/` |
| | Sources | `/sources/` |
| | Health | `/health/` |
| | Ingestion Stats | `/health/ingestion` |
| | SLO | `/slo/` |
| | Services | `/services/` |
| | Topology | `/topology/` |
| **Learn** | Knowledge Base | `/knowledge/` |
| | Metrics | `/metrics/` |
| | Analytics | `/analytics/` |
| | Reports | `/reports/executive` |
| | Handoff | `/handoff/` |
| **Manage** | Spending | `/spending/` |
| | Cost Insights | `/spending/costs` |
| | Notifications | `/notifications/` |
| | Trust | `/settings/trust/` |

The grouping itself (Observe/Learn/Manage) is a candidate for revision — assess
whether it helps or hinders an SRE under pressure.

---

## 7. Screen / template inventory

Top-level pages by feature area (each has supporting `_partial.html` fragments
swapped in via HTMX). Source: `ui/beeper_ui/templates/`.

- **investigations/** — list + detail. The core surface. Detail is rich:
  findings, recommendations, evidence panel + timeline, confidence gate,
  deploy correlation, service topology, collaboration panel, remediation
  progress, feedback/confirmation/resolution forms, urgency card. **Spend the
  most effort here.**
- **knowledge/** — KB wiki: index, entry, edit, diff, history, version,
  per-service knowledge, trust settings, import, learning adjustments,
  corrections, search/filter.
- **health/** — `status` and `ingestion` dashboards.
- **services/** — list + detail + health feed.
- **slo/** — dashboard + per-service SLO.
- **topology/** — dependency graph + service cards.
- **sources/** — connected observability backends list.
- **analytics/** — dashboard.
- **metrics/** — MTTR trends + drilldown.
- **reports/** — executive report + noise report.
- **spending/** — spend overview + cost breakdown.
- **trust/** — autonomy settings, gate thresholds, adaptive tuning, history.
- **notifications/** — channel config + test.
- **handoff/** — shift handoff summary.
- **components/** — shared: `layout.html` (shell), `sidebar.html`, `cards.html`,
  `status.html`, `empty.html`, `diagnostic.html`, `_command_palette.html`,
  `_keyboard_help.html`. **Changes here propagate everywhere — high leverage.**

Full file-level list: `find ui/beeper_ui/templates -name '*.html'` (112 files).

---

## 8. Review & revision checklist

Per screen, work through:

- [ ] **Purpose is obvious** — a one-line "what this is / why it matters" is
      clear from the page itself (title, intro, or empty state).
- [ ] **SRE-readable labels** — no internal/model jargon; consistent with the
      glossary you build (Section 2).
- [ ] **Information hierarchy** — most-urgent info first; severity/status legible
      at a glance using the status tokens.
- [ ] **Empty / loading / error states** exist and are helpful (reuse
      `components/empty.html`).
- [ ] **Visual consistency** — spacing scale, type scale, card/table patterns,
      button styles reused, not reinvented.
- [ ] **Accessibility** — contrast passes, focus visible, keyboard reachable,
      ARIA/`sr-only` correct, command palette + sidebar usable by keyboard.
- [ ] **Responsive** — works at `sm`/`lg`/`xl`; sidebar rail collapse and
      command palette behave on small screens.
- [ ] **HTMX swaps** — partial updates don't flash/jump; transitions feel intentional.

Deliver a **glossary / terminology map** and, if IA changes, an updated nav
proposal as part of the work.

---

## 9. Working agreement

- **Branch:** commit to `claude/handoff-design-lknw65`. Open small, reviewable
  draft PRs (per feature area or per cross-cutting concern) rather than one
  mega-PR.
- **Don't break tests.** There's an extensive template/route test suite:
  ```bash
  cd ui && poetry run pytest
  ```
  Several tests assert on rendered markup and labels (e.g.
  `test_sidebar_navigation.py`, `test_layout_shell.py`,
  `test_page_template_rendering.py`). If you rename a label or restructure
  markup, **update the corresponding test** in the same PR and say so.
- **Lint/type-check:** `poetry run ruff check .` and `poetry run mypy .`.
- **CSS:** rebuild with `make tailwind-build` (or `tailwind-watch`); never commit
  `tailwind.css` (gitignored).
- **Verify visually:** run `python demo_ui.py` and confirm the affected screens.
- **When intent is unclear**, read the implementation artifact for that feature
  in `_bmad-output/implementation-artifacts/` (named like `4-1-investigation-list-view.md`)
  before guessing — then propose clearer language rather than preserving jargon.

---

## 10. Key files at a glance

| What | Where |
|---|---|
| Design tokens / Tailwind config | `ui/beeper_ui/static/css/input.css` |
| Legacy CSS (careful) | `ui/beeper_ui/static/css/main.css` (~7k lines) |
| App shell / layout | `ui/beeper_ui/templates/components/layout.html` |
| Sidebar + nav items | `ui/beeper_ui/templates/components/sidebar.html`, `layout.html` |
| Base template | `ui/beeper_ui/templates/base.html` |
| Standalone preview | `ui/demo_ui.py` |
| UX spec (canonical) | `docs/specs/ux-design-specification.md` |
| Feature intent / artifacts | `_bmad-output/implementation-artifacts/` |
| Tests | `ui/tests/` |
</content>
</invoke>
