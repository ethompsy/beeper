import type { StepEvidence as StepEvidenceValue } from '../../../api/investigation-detail'
import { cn } from '../../utils/cn'

/**
 * StepEvidence — inline evidence renderer for an `InvestigationStep`'s
 * evidence slot (FR25; docs/specs/ux-design-specification.md §5 "Evidence
 * rendering"): metric values in `<code class="font-mono text-sm">`, log
 * excerpts in `<pre class="font-mono text-sm overflow-x-auto max-h-32">`.
 *
 * A thin, reusable formatter so `InvestigationDetailPage` (Task 2.5) doesn't
 * hand-roll this markup per step, and so it stays consistent if a future
 * view (e.g. a permalinked step anchor, Task 3.2) needs the same rendering.
 */
export interface StepEvidenceProps {
  evidence: StepEvidenceValue[]
  className?: string
}

export function StepEvidence({ evidence, className }: StepEvidenceProps) {
  if (evidence.length === 0) return null

  return (
    <div data-slot="step-evidence-list" className={cn('flex flex-col gap-1', className)}>
      {evidence.map((item, index) =>
        item.kind === 'metric' ? (
          <code
            key={index}
            data-evidence-kind="metric"
            className="font-mono text-sm text-text-primary"
          >
            {item.query}: {item.value}
          </code>
        ) : (
          <pre
            key={index}
            data-evidence-kind="log"
            className="max-h-32 overflow-x-auto font-mono text-sm text-text-primary"
          >
            {item.excerpt}
          </pre>
        ),
      )}
    </div>
  )
}
