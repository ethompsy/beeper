import { useEffect, useRef, useState } from 'react'
import { fetchKnowledgeEntry, type KnowledgeEntryDetailDto } from '../api/knowledge-detail'

/**
 * useKnowledgeEntry — one-shot fetch lifecycle for the KB entry-detail view
 * (Task 5.1). Mirrors `useInvestigationDetail.ts` exactly (same
 * loading/ok/not-found/error state shape, same stale-response guard via a
 * request-id ref) so `KnowledgeEntryPage` follows the identical render
 * pattern `InvestigationDetailPage` already established.
 */
export type KnowledgeEntryQueryState =
  | { status: 'loading' }
  | { status: 'ok'; data: KnowledgeEntryDetailDto }
  | { status: 'not-found' }
  | { status: 'error' }

export function useKnowledgeEntry(entryId: string | undefined): KnowledgeEntryQueryState {
  const [state, setState] = useState<KnowledgeEntryQueryState>({ status: 'loading' })
  // Guards against a stale response from a previous id landing after the id
  // has already changed (e.g. rapid navigation between two entry permalinks).
  const requestIdRef = useRef(0)

  useEffect(() => {
    if (entryId == null) {
      setState({ status: 'not-found' })
      return
    }

    setState({ status: 'loading' })
    const requestId = ++requestIdRef.current

    fetchKnowledgeEntry(entryId).then((result) => {
      if (requestIdRef.current !== requestId) return // superseded by a newer request

      if (result.kind === 'ok') {
        setState({ status: 'ok', data: result.data })
      } else if (result.kind === 'not-found') {
        setState({ status: 'not-found' })
      } else {
        setState({ status: 'error' })
      }
    })
  }, [entryId])

  return state
}
