import { useParams } from 'react-router-dom'

/**
 * KnowledgeEntryPage — route scaffolding placeholder (Task 5.0b).
 *
 * Placeholder — Task 5.1 replaces this file's implementation with the real
 * Knowledge Base entry detail view (`/app/knowledge/:entryId`, per
 * docs/design/route-parity-targets.md §2). Renders only an honest
 * "not yet migrated" notice inside the shell — nothing here should be
 * mistaken for the finished feature.
 */
export function KnowledgeEntryPage() {
  const { entryId } = useParams<{ entryId: string }>()

  return (
    <div data-testid="knowledge-entry-page" className="flex flex-col gap-2">
      <h1 className="text-2xl font-semibold text-text-primary">Knowledge Base Entry</h1>
      <p className="text-sm text-text-secondary">
        {entryId ? `Entry ${entryId} has not` : 'This entry has not'} been migrated to React yet.
      </p>
    </div>
  )
}
