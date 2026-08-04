import { cn } from '../../utils/cn'

/**
 * FailureNotice — visually distinct block appended after the completed
 * steps of a Failed investigation (FR23; glossary job-phase "Analysis
 * Failed"). Deliberately NOT the `conclusion_block` — a Failed investigation
 * never renders a conclusion (no root cause / affected services / signal
 * count to report), only this notice.
 *
 * Visually parallels `InvestigationStep`'s surface treatment but uses the
 * critical status color so it reads as distinct from a normal step, per
 * the spec's "visually distinct failure notice" requirement.
 */
export interface FailureNoticeProps {
  /** Optional detail message (e.g. the last error the investigator pipeline reported). */
  message?: string | null
  className?: string
}

export function FailureNotice({ message, className }: FailureNoticeProps) {
  return (
    <div
      data-slot="failure-notice"
      role="alert"
      className={cn(
        'flex flex-col gap-1 border-l-2 border-l-status-critical bg-surface-overlay p-3',
        className,
      )}
    >
      <span className="text-sm font-semibold text-status-critical">Analysis Failed</span>
      <p className="text-base text-text-primary">
        {message ?? 'The investigation could not be completed.'}
      </p>
    </div>
  )
}
