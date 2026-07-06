/**
 * investigations-list.ts — plain-`fetch` client for the Task 1.6 JSON list
 * endpoint (`GET /api/v1/investigations`).
 *
 * Deliberately dependency-free (no react-query/swr) per Task 2.2's scope
 * discipline note: a data-fetching library is out of scope here to avoid
 * conflicting with the parallel Task 2.5 (detail view REST client). Task 2.5
 * owns `investigations/{id}`; this module owns the list endpoint only.
 *
 * Response shape mirrors `investigations_list_json()` in
 * `ui/beeper_ui/routes/investigations.py` exactly (Task 1.6):
 *   id, status, service, severity, condition, started_at, triggered_at,
 *   completed_at, workflow_state, workflow_state_changed_at.
 */

/** Job-phase status values the operator emits (`InvestigationService.list_investigations`). */
export type InvestigationStatus = 'investigating' | 'awaiting_confirmation' | 'completed' | 'failed'

/** Workflow-state values — a separate axis from job-phase `status` (glossary OD-1). */
export type WorkflowState = 'detected' | 'investigating' | 'resolved' | 'verified' | 'failed'

export type InvestigationSeverity = 'low' | 'medium' | 'high' | 'critical'

export interface InvestigationListItem {
  id: string
  status: InvestigationStatus
  service: string
  severity: InvestigationSeverity
  /** Raw condition field — "Affected component"/problem-state derivation is Task 2.3/2.4's scope, not this one. */
  condition: string | null
  started_at: string | null
  triggered_at: string | null
  completed_at: string | null
  workflow_state: WorkflowState | null
  workflow_state_changed_at: string | null
}

export interface InvestigationListParams {
  /** Job-phase status filter — matches `VALID_STATUSES` server-side. */
  status?: InvestigationStatus
  service?: string
  severity?: InvestigationSeverity
}

export class InvestigationsListError extends Error {
  readonly status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'InvestigationsListError'
    this.status = status
  }
}

const LIST_ENDPOINT = '/api/v1/investigations/'

function buildQuery(params: InvestigationListParams | undefined): string {
  if (!params) return ''
  const search = new URLSearchParams()
  if (params.status) search.set('status', params.status)
  if (params.service) search.set('service', params.service)
  if (params.severity) search.set('severity', params.severity)
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

/**
 * Fetch the investigation list from the Task 1.6 JSON API.
 *
 * Filtering here is limited to the server-supported `status`/`service`/
 * `severity` query params. The status-*group* filter (active/resolved/failed)
 * used by the list UI is applied client-side (see `status-group.ts`) since
 * the group is a UI grouping concept the server doesn't expose as its own
 * param on this endpoint — this keeps the filter logic factored so Task 3.1
 * can lift it into the URL without touching this client.
 */
export async function fetchInvestigations(
  params?: InvestigationListParams,
  signal?: AbortSignal,
): Promise<InvestigationListItem[]> {
  const response = await fetch(`${LIST_ENDPOINT}${buildQuery(params)}`, { signal })

  if (!response.ok) {
    throw new InvestigationsListError(
      `Failed to fetch investigations (HTTP ${response.status})`,
      response.status,
    )
  }

  const data = (await response.json()) as InvestigationListItem[] | { error: string }
  if (!Array.isArray(data)) {
    throw new InvestigationsListError(data.error ?? 'Unable to connect to the Beeper operator.')
  }

  return data
}
