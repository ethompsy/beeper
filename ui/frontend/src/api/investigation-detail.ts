/**
 * investigation-detail.ts — REST client for `GET /api/v1/investigations/{id}`
 * (Task 1.6; owned by Task 2.5 per Plan §Task 2.5 "This task OWNS the detail
 * REST client"). Plain `fetch`, no react-query — Task 2.2's list view avoids
 * adding a fetch library too, so this stays consistent across the app.
 *
 * Task 2.6 (SSE reconnect backfill, AD-4) re-uses `fetchInvestigationDetail`
 * to diff/insert steps missed during a disconnect — the response shape here
 * must stay stable for that reuse.
 *
 * ── Response shape (Task 1.6) ──────────────────────────────────────────
 * The backend endpoint (`ui/beeper_ui/routes/investigations.py`,
 * `investigation_detail_json`) returns:
 *   { id, status, service, message,
 *     metadata: { id, status, service, severity, condition, message,
 *                 started_at, triggered_at, completed_at, workflow_state,
 *                 workflow_state_changed_at, signal_count, job_name },
 *     steps: [ { order, key, label, state, type }, ... ] }
 *
 * Evidence values (inline Prometheus/Loki content, FR25) and Related KB
 * entries (FR26) are NOT yet part of this endpoint's payload — the richer
 * per-step evidence and linked-KB-entry data currently lives only in
 * Jinja-only service paths (`evidence_service`, `kb_service`) that are not
 * exposed via this JSON API. The types below model `evidence` (per step)
 * and `kbEntries` (per KB-type step) as OPTIONAL/forward-compatible fields
 * so the detail view renders them the moment the backend adds them,
 * without requiring a client change — and degrades gracefully (no evidence
 * block; "0 Related KB Entries") when they're absent, exactly as FR26
 * specifies for the "absent or unparseable" case. See the Task 2.5 report
 * for the follow-up to close this gap with the backend.
 */

/** Job-phase status string as returned by the operator (`InvestigationPhase`). */
import { apiFetch } from './http'

export type InvestigationDetailStatus =
  | 'pending'
  | 'investigating'
  | 'awaiting_confirmation'
  | 'completed'
  | 'failed'
  | string

export type InvestigationStepState = 'completed' | 'active' | 'pending' | 'error'

export type InvestigationStepApiType =
  | 'metric'
  | 'log'
  | 'deploy'
  | 'kb'
  | 'correlation'
  | 'summary'
  | string

/** A single inline evidence value (Prometheus metric reading). FR25. */
export interface MetricEvidence {
  kind: 'metric'
  query: string
  value: string
}

/** A single inline evidence value (Loki log excerpt). FR25. */
export interface LogEvidence {
  kind: 'log'
  query: string
  excerpt: string
}

export type StepEvidence = MetricEvidence | LogEvidence

/** One related Knowledge Base entry surfaced by a KBQueryStep. FR26. */
export interface RelatedKbEntry {
  id: string
  title: string
}

export interface InvestigationStepDto {
  order: number
  key: string | null
  label: string | null
  state: InvestigationStepState
  type: InvestigationStepApiType
  /** Forward-compatible: absent today (see module doc). */
  evidence?: StepEvidence[]
  /** Forward-compatible: present only on `type === 'kb'` steps, if at all. */
  kbEntries?: RelatedKbEntry[]
}

export interface InvestigationDetailMetadata {
  id: string
  status: InvestigationDetailStatus
  service: string
  severity: string | null
  condition: string | null
  message: string | null
  started_at: string | null
  triggered_at: string | null
  completed_at: string | null
  workflow_state: string | null
  workflow_state_changed_at: string | null
  signal_count: number | null
  job_name: string | null
  /**
   * Cross-service correlation (FR48). Gated on RFC 0001 Phase 3 — the
   * operator produces no `correlatedServices`/`downstream[]` fields today,
   * so this is always absent in practice; the view renders the "impact:
   * not yet correlated" placeholder until the backend ships it.
   */
  correlated_services?: string[]
}

export interface InvestigationDetailDto {
  id: string
  status: InvestigationDetailStatus
  service: string
  message: string | null
  metadata: InvestigationDetailMetadata
  steps: InvestigationStepDto[]
}

export type InvestigationDetailResult =
  | { kind: 'ok'; data: InvestigationDetailDto }
  | { kind: 'not-found' }
  | { kind: 'error'; error: unknown }

/**
 * Fetch investigation detail JSON for `investigationId`.
 *
 * Never throws — network failures, non-2xx responses (other than 404), and
 * JSON parse errors all resolve to `{ kind: 'error' }` so the view can
 * render a retry-safe error state instead of an unhandled rejection. A 404
 * response resolves to the distinct `{ kind: 'not-found' }` variant so the
 * view can render "Investigation not found" (in-shell, per the Task 2.5 AC)
 * rather than a generic error.
 */
export async function fetchInvestigationDetail(
  investigationId: string,
  init?: RequestInit,
): Promise<InvestigationDetailResult> {
  let response: Response
  try {
    response = await apiFetch(
      `/api/v1/investigations/${encodeURIComponent(investigationId)}`,
      init,
    )
  } catch (error) {
    // Also catches `apiFetch`'s `PermissionDeniedError` (403) — this
    // function's `{ kind: 'error', error }` contract already carries the
    // thrown value through untouched, so callers CAN narrow on
    // `error instanceof PermissionDeniedError` without any shape change
    // here (Task 8.4).
    return { kind: 'error', error }
  }

  if (response.status === 404) {
    return { kind: 'not-found' }
  }

  if (!response.ok) {
    return { kind: 'error', error: new Error(`Unexpected status ${response.status}`) }
  }

  try {
    const data = (await response.json()) as InvestigationDetailDto
    return { kind: 'ok', data }
  } catch (error) {
    return { kind: 'error', error }
  }
}
