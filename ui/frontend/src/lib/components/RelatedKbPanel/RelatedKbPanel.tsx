import * as Collapsible from '@radix-ui/react-collapsible'
import type { ReactNode } from 'react'
import { cn } from '../../utils/cn'

/**
 * RelatedKbPanel — always-visible anchored bar showing related KB entry
 * count, expands upward on click (docs/specs/ux-design-specification.md
 * §10 `kb_panel` macro).
 *
 * SKELETON (Task 1.4): correct props + token-based styling + Storybook
 * story per state. Built on Radix `Collapsible` for accessible
 * expand/collapse (`aria-expanded`, keyboard support) — this is the one
 * Radix primitive this component needs; the anchored-bottom-bar vs.
 * inline-below-content responsive behavior (>=1200px vs <1200px) is a
 * layout-shell concern wired in Task 2.1/2.5, not this primitive.
 *
 * "Loading" vs "0 entries" is an intentional distinct state (spec
 * rationale): loading = "still looking" (trust), zero = "checked, found
 * nothing" (information). Both are represented explicitly below.
 */
export type RelatedKbPanelState = 'loading' | 'populated' | 'zero'

export interface RelatedKbPanelProps {
  /** Explicit state — loading (KBQueryStep in progress) vs. populated vs. zero entries. */
  state: RelatedKbPanelState
  /** Entry count. Ignored when `state === 'loading'`. */
  entryCount: number
  /** Controlled expanded state (bare skeleton — Milestone 1.2 wires real open/close + responsive stacking). */
  expanded?: boolean
  /** Called when the trigger is activated (skeleton passthrough — no internal state management yet). */
  onExpandedChange?: (expanded: boolean) => void
  /** Panel content shown when expanded (KB entry list) — rendering left to the caller. */
  children?: ReactNode
}

export function RelatedKbPanel({
  state,
  entryCount,
  expanded = false,
  onExpandedChange,
  children,
}: RelatedKbPanelProps) {
  const label =
    state === 'loading'
      ? 'Checking knowledge base...'
      : `${entryCount} Related KB Entries`

  return (
    <Collapsible.Root
      data-slot="related-kb-panel"
      data-state={state}
      open={expanded}
      onOpenChange={onExpandedChange}
      className="border-t border-surface-overlay bg-surface-raised"
    >
      <section aria-label="Related knowledge base entries">
        <Collapsible.Trigger
          disabled={state === 'loading'}
          aria-expanded={expanded}
          className={cn(
            'flex w-full items-center justify-between px-4 py-2 text-left text-sm text-text-secondary',
            state === 'loading' && 'animate-pulse motion-reduce:animate-none',
          )}
        >
          <span>{label}</span>
          {state !== 'loading' ? <span aria-hidden="true">&#9652;</span> : null}
        </Collapsible.Trigger>
        {/*
          Spec calls for max-height: 50vh on the expanded panel. Tailwind's
          default max-h scale has no fractional-viewport step and using an
          arbitrary value (max-h-[50vh]) is blocked by the FR51 lint gate.
          max-h-96 (24rem) is a token-safe skeleton stand-in; Milestone 1.2
          should revisit with a real viewport-relative token if needed.
        */}
        <Collapsible.Content className="max-h-96 overflow-y-auto px-4 pb-4">
          {children}
        </Collapsible.Content>
      </section>
    </Collapsible.Root>
  )
}
