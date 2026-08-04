import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '../../utils/cn'

/**
 * InvestigationStep — one step in the investigation evidence timeline
 * (docs/specs/ux-design-specification.md §5 `investigation_step` macro).
 *
 * SKELETON (Task 1.4): correct props + token-based styling + Storybook
 * story. Real SSE-driven append/reorder/first-evidence-emphasis wiring
 * lands with Task 2.5/2.6a (Milestone 1.2).
 */
export type InvestigationStepType =
  | 'metric'
  | 'log'
  | 'deploy'
  | 'kb'
  | 'correlation'
  | 'summary'

const STEP_TYPE_LABEL: Record<InvestigationStepType, string> = {
  metric: 'Metric Query',
  log: 'Log Query',
  deploy: 'Deploy',
  kb: 'KB Query',
  correlation: 'Correlation',
  summary: 'Summary',
}

/** Step-type border colors — consume the step-* tokens from tokens.css (Task 1.2), never redeclare. */
const STEP_TYPE_BORDER: Record<InvestigationStepType, string> = {
  metric: 'border-l-step-metric',
  log: 'border-l-step-log',
  deploy: 'border-l-step-log', // deploy events share the log-evidence accent; no dedicated token yet
  kb: 'border-l-step-kb',
  correlation: 'border-l-step-correlation',
  summary: 'border-l-step-summary',
}

export interface InvestigationStepProps extends HTMLAttributes<HTMLLIElement> {
  /** Step type — drives left-border color + evidence-type badge label. */
  type: InvestigationStepType
  /** Sortable sequence number (see spec: used to detect out-of-order backfill inserts). */
  order: number
  /** Step description (text-base). Free-text from the investigator pipeline. */
  description: string
  /**
   * Evidence content (monospace metric values, log excerpts, service-name
   * chips). Rendering of the evidence block's internal structure is left to
   * the caller — this component only provides the slot + spacing.
   */
  evidence?: ReactNode
  /**
   * True for the first step carrying real evidence — receives the
   * "trust-ignition" emphasis treatment (surface-overlay background,
   * settles to surface-raised over `--duration-emphasis`). Reduced-motion:
   * settles instantly (see the `motion-reduce:` class below).
   */
  isFirstEvidence?: boolean
}

export function InvestigationStep({
  type,
  order,
  description,
  evidence,
  isFirstEvidence = false,
  className,
  ...rest
}: InvestigationStepProps) {
  return (
    <li
      data-slot="investigation-step"
      data-step-type={type}
      data-order={order}
      className={cn(
        // See InvestigationCard for the border-l-2 vs. spec's 3px note.
        'flex flex-col gap-1 border-l-2 bg-surface-raised p-3',
        'transition-colors duration-emphasis motion-reduce:transition-none',
        STEP_TYPE_BORDER[type],
        isFirstEvidence && 'bg-surface-overlay',
        className,
      )}
      {...rest}
    >
      {/* D2 (density audit §15, user-approved): summary steps carry no type
          badge — the approved glossary says the summary IS the content, a
          "Summary" label above it is redundant chrome. All other types keep
          their evidence-type badge. */}
      {type !== 'summary' ? (
        <span className="text-xs text-text-secondary">{STEP_TYPE_LABEL[type]}</span>
      ) : null}
      <p className="text-base text-text-primary">{description}</p>
      {evidence != null ? <div data-slot="step-evidence">{evidence}</div> : null}
    </li>
  )
}
