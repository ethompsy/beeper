import { useParams } from 'react-router-dom'

/**
 * InvestigationDetailPage — Task 2.1 route placeholder.
 *
 * Minimal content only: the real detail view (summary header, evidence
 * steps, KB panel, SSE) is Task 2.5's scope. This page exists so the shell
 * can route to `/investigations/:id` and so the focus-management contract
 * (focus → summary `<h1>` on detail-route entry, per WCAG 2.4.3) has a
 * concrete heading to target.
 *
 * `id="detail-summary-heading"` is the contract `useRouteFocusManagement`
 * targets — Task 2.5's real `SummaryHeader` usage must carry this same id
 * on its `<h1>` so focus management keeps working once the placeholder is
 * replaced with real content.
 */
export function InvestigationDetailPage() {
  const { investigationId } = useParams<{ investigationId: string }>()

  return (
    <div data-testid="investigation-detail-page">
      <h1 id="detail-summary-heading" className="text-2xl font-semibold text-text-primary">
        {investigationId}
      </h1>
      <p className="mt-2 text-text-secondary">Detail view placeholder — Task 2.5 builds this out.</p>
    </div>
  )
}
