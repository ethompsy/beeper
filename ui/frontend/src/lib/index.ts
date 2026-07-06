/**
 * Beeper component library — public API barrel (Task 1.4).
 *
 * This is the ONE entry point built to `dist-lib/` and consumed by:
 *  (a) external tooling (`/design-sync`, per DESIGN_SYNC.md), and
 *  (b) Milestone 1.2 views, which import library primitives from here
 *      rather than reaching into `src/lib/components/*` directly — this
 *      file IS the extraction boundary. A component only "graduates" into
 *      the library (and gets exported here) once it is a reusable,
 *      token-styled, Storybook-documented primitive; page-local JSX that
 *      isn't reused stays in the view and is never added to this barrel.
 *
 * Every named export here must have:
 *   1. A typed props interface (also exported).
 *   2. Token-based styling only (no hardcoded values — enforced by the
 *      Task 1.2 lint config, which scopes to `src/**\/*.{ts,tsx}` and
 *      therefore covers this directory too).
 *   3. A Storybook story under `src/lib/components/<Name>/`.
 */

export { cn } from './utils/cn'

export { InvestigationCard } from './components/InvestigationCard'
export type {
  InvestigationCardProps,
  InvestigationCardVariant,
} from './components/InvestigationCard'

export { StatusBadge } from './components/StatusBadge'
export type { StatusBadgeProps, StatusBadgeVariant } from './components/StatusBadge'

export { InvestigationStep } from './components/InvestigationStep'
export type {
  InvestigationStepProps,
  InvestigationStepType,
} from './components/InvestigationStep'

export { SummaryHeader } from './components/SummaryHeader'
export type { SummaryHeaderProps } from './components/SummaryHeader'

export { RelatedKbPanel } from './components/RelatedKbPanel'
export type {
  RelatedKbPanelProps,
  RelatedKbPanelState,
} from './components/RelatedKbPanel'

export { StepEvidence } from './components/StepEvidence'
export type { StepEvidenceProps } from './components/StepEvidence'

export { FailureNotice } from './components/FailureNotice'
export type { FailureNoticeProps } from './components/FailureNotice'

export { NotFoundMessage } from './components/NotFoundMessage'
export type { NotFoundMessageProps } from './components/NotFoundMessage'

export { DetailSkeleton } from './components/DetailSkeleton'
export type { DetailSkeletonProps } from './components/DetailSkeleton'

export { Sidebar } from './components/Sidebar'
export type {
  SidebarProps,
  SidebarGroupData,
  SidebarNavItem,
  SidebarLinkProps,
} from './components/Sidebar'

export { AppShell } from './components/AppShell'
export type { AppShellProps } from './components/AppShell'

export { useSidebarState } from './hooks/useSidebarState'
export type { SidebarState, SidebarRouteMode } from './hooks/useSidebarState'

export { useRouteFocusManagement } from './hooks/useRouteFocusManagement'

export { useIsNarrowViewport } from './hooks/useIsNarrowViewport'
