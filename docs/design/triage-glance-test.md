# Triage-Glance Acceptance Test (Task 4.3, NFR19 / `[H]`)

**What this proves:** an on-call SRE shown an investigation cold can answer
"what is wrong and how bad is it?" from the first-seconds facts alone —
no scrolling, no clicking, no prompting.

## Setup (already running)

```bash
# from repo root — serves the built React UI with mocked incidents on :5050
cd ui && poetry run python demo_ui.py
# (or via the Claude preview: launch config "beeper-demo")
```

The frontend must be built first: `cd ui/frontend && npm run build`.

## Protocol

- **Reviewers:** 2 people who did **not** build this UI and have not seen it before.
- **Per incident:** open the permalink cold (fresh tab), start a 5-second count,
  then ask the reviewer to name — unprompted:
  1. **Service** (which app/service is affected)
  2. **Problem state** (what is wrong, in their own words — matching the gist counts)
  3. **Severity** (critical / high / medium / low)
- "Affected component" is **NOT** in the 5-second bar this increment (D7/Q2).
- **Pass bar:** each reviewer names all 3 facts within 5 s on **every** incident.
  **Any miss → fail** → triggers a language/layout iteration, then re-test.

## Incidents (≥3 distinct, mixed severity/status)

| # | Permalink | Expected: service | Expected: problem state (gist) | Expected: severity |
|---|-----------|-------------------|-------------------------------|--------------------|
| 1 | `http://localhost:5050/app/investigations/inv-2026-087` | payments | HTTP 5xx error rate elevated (18%) | critical |
| 2 | `http://localhost:5050/app/investigations/inv-2026-086` | auth-service | Elevated latency (p99 > 5s) | high |
| 3 | `http://localhost:5050/app/investigations/inv-2026-085` | catalog | High memory usage (90%) | medium |
| spare | `http://localhost:5050/app/investigations/inv-2026-084` | notifications | Increased queue depth | low |

## Results

| Incident | Reviewer A — service / problem / severity (✓/✗ each, time) | Reviewer B — service / problem / severity (✓/✗ each, time) |
|----------|--------------------------------------------------------------|--------------------------------------------------------------|
| 1 (payments) | | |
| 2 (auth-service) | | |
| 3 (catalog) | | |

**Reviewers (names/roles):** _________________
**Date/witness:** _________________
**Verdict:** ☐ PASS (all facts, all incidents, both reviewers ≤5 s) ☐ FAIL → iteration notes below

**Iteration notes (if any miss):**
