import type { HTMLAttributes } from 'react'
import { cn } from '../../utils/cn'

/**
 * StatusBadge — the single status-indicator primitive used across every
 * view (investigation list/detail, ingestion stats, sidebar).
 *
 * SKELETON (Task 1.4): correct props + token-based styling + Storybook
 * story. Real usage wiring (deriving `variant` from CRD fields) lands with
 * the views in Milestone 1.2.
 *
 * ── Variant taxonomy (docs/design/terminology-glossary.md + ux-design-specification.md §7) ──
 *
 * StatusBadge is deliberately a single component with one flat `variant`
 * union rather than three separate badge components, because the visual
 * language (bg token @ 10% opacity + matching text token, pill shape) is
 * identical across all of them — only the color mapping + label differ.
 * Views select the right `variant` value for the field they're rendering;
 * this component owns no business logic about *which* CRD field maps to
 * *which* variant (that mapping is Milestone 1.2's job, e.g. Task 2.2/2.5).
 *
 * The variant set spans three distinct glossary axes that visually reuse
 * the same 4 status colors — call sites must pick the variant for the
 * *specific* field they're rendering, since the same word ("Failed") maps
 * to two different variants depending on which axis is in play:
 *
 * 1. Job phase   (`InvestigationPhase`): investigating | awaiting-confirmation
 *                | completed | analysis-failed | pending
 *      - Glossary OD-1: job-phase `Failed` renders label **"Analysis Failed"**
 *        (variant `analysis-failed`) — distinct from workflow-state `Failed`.
 * 2. Workflow state (`WorkflowState`): detected | investigating | resolved
 *                | verified | failed
 *      - Workflow-state `Failed` (variant `failed`) renders label **"Failed"**
 *        (no rename — glossary OD-1) but is a SEPARATE variant token from
 *        `analysis-failed` so call sites cannot conflate the two axes.
 * 3. Pipeline / diagnostic health: healthy | warning | critical | warming-up
 *      - Used by the Ingestion Stats / EWMA diagnostic tiles (not
 *        investigation-scoped), reusing the same color language.
 *
 * Severity (`Low`/`Medium`/`High`/`Critical`) is NOT a StatusBadge variant —
 * per the glossary (§11) severity is its own tag with its own copy; only its
 * `critical` value maps onto the shared critical color, exposed here as the
 * `severity-critical` variant alias for visual consistency when a severity
 * tag needs the same pill treatment. `low`/`medium`/`high` map to `muted`,
 * `warning`-adjacent, and `warning` respectively — call sites pass the
 * severity string as `label` with the closest color variant.
 */
export type StatusBadgeVariant =
  // Job phase (InvestigationPhase)
  | 'investigating'
  | 'awaiting-confirmation'
  | 'completed'
  | 'analysis-failed'
  | 'pending'
  // Workflow state (WorkflowState) — Failed here is its OWN variant, see above
  | 'detected'
  | 'resolved'
  | 'verified'
  | 'failed'
  // Pipeline / diagnostic health
  | 'healthy'
  | 'warning'
  | 'critical'
  | 'warming-up'
  | 'no-data'

export interface StatusBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  /** Which status axis + value this badge represents (see variant taxonomy above). */
  variant: StatusBadgeVariant
  /**
   * Display label. Optional — when omitted, falls back to the standardized
   * glossary label for `variant` (see `STATUS_BADGE_LABELS`). Views pass an
   * explicit `label` only when the glossary label doesn't fit the exact
   * source string (e.g. severity tags, which aren't in the variant table).
   */
  label?: string
}

/** Standardized labels per docs/design/terminology-glossary.md. */
const STATUS_BADGE_LABELS: Record<StatusBadgeVariant, string> = {
  investigating: 'Investigating',
  'awaiting-confirmation': 'Awaiting Confirmation',
  completed: 'Completed',
  'analysis-failed': 'Analysis Failed', // glossary OD-1: job-phase Failed
  pending: 'Pending',
  detected: 'Detected',
  resolved: 'Resolved',
  verified: 'Verified',
  failed: 'Failed', // glossary OD-1: workflow-state Failed (KEEP, no rename)
  healthy: 'Healthy',
  warning: 'Warning',
  critical: 'Critical',
  'warming-up': 'Warming Up',
  'no-data': 'No Data',
}

/** Token classes per variant — bg token @ 10% opacity + matching text token. */
const STATUS_BADGE_STYLES: Record<StatusBadgeVariant, string> = {
  investigating: 'bg-status-healthy/10 text-status-healthy',
  'awaiting-confirmation': 'bg-status-warning/10 text-status-warning',
  completed: 'bg-status-muted/10 text-status-muted',
  'analysis-failed': 'bg-status-critical/10 text-status-critical',
  pending: 'bg-status-muted/10 text-status-muted',
  detected: 'bg-primary/10 text-primary',
  resolved: 'bg-status-healthy/10 text-status-healthy',
  verified: 'bg-status-healthy/10 text-status-healthy',
  failed: 'bg-status-critical/10 text-status-critical',
  healthy: 'bg-status-healthy/10 text-status-healthy',
  warning: 'bg-status-warning/10 text-status-warning',
  critical: 'bg-status-critical/10 text-status-critical',
  'warming-up': 'bg-status-warning/10 text-status-warning',
  'no-data': 'bg-status-critical/10 text-status-critical',
}

export function StatusBadge({ variant, label, className, ...rest }: StatusBadgeProps) {
  return (
    <span
      data-slot="status-badge"
      data-variant={variant}
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
        STATUS_BADGE_STYLES[variant],
        className,
      )}
      {...rest}
    >
      {label ?? STATUS_BADGE_LABELS[variant]}
    </span>
  )
}
