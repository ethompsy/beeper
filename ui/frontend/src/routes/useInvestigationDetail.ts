import { useEffect, useRef, useState } from 'react'
import { fetchInvestigationDetail, type InvestigationDetailDto } from '../api/investigation-detail'

/**
 * useInvestigationDetail — one-shot fetch lifecycle for the detail view's
 * initial render (Task 2.5 scope). LIVE streaming (SSE) is Task 2.6 — this
 * hook only performs the single `GET /api/v1/investigations/{id}` request
 * on mount / id change and exposes a plain loading/data/notFound/error
 * state tuple for the view to render from.
 *
 * Deliberately not react-query (see `src/api/investigation-detail.ts` doc):
 * the fetch/state shape needed here is small enough that a bespoke hook
 * keeps the dependency surface flat, matching the parallel Task 2.2 list
 * view's own no-fetch-library constraint.
 */
export type InvestigationDetailQueryState =
  | { status: 'loading' }
  | { status: 'ok'; data: InvestigationDetailDto }
  | { status: 'not-found' }
  | { status: 'error' }

export function useInvestigationDetail(investigationId: string | undefined): InvestigationDetailQueryState {
  const [state, setState] = useState<InvestigationDetailQueryState>({ status: 'loading' })
  // Guards against a stale response from a previous id landing after the id
  // has already changed (e.g. rapid navigation between two detail permalinks).
  const requestIdRef = useRef(0)

  useEffect(() => {
    if (investigationId == null) {
      setState({ status: 'not-found' })
      return
    }

    setState({ status: 'loading' })
    const requestId = ++requestIdRef.current

    fetchInvestigationDetail(investigationId).then((result) => {
      if (requestIdRef.current !== requestId) return // superseded by a newer request

      if (result.kind === 'ok') {
        setState({ status: 'ok', data: result.data })
      } else if (result.kind === 'not-found') {
        setState({ status: 'not-found' })
      } else {
        setState({ status: 'error' })
      }
    })
  }, [investigationId])

  return state
}
