/**
 * TokenSwatch — Design-system token smoke-test component.
 *
 * Purpose: prove that Tailwind token classes (bg-surface-base, text-primary,
 * etc.) resolve to the correct design-system hex values at build time.
 * Used by token-resolution tests; not a production UI component.
 *
 * NFR22 / FR51 compliance demonstrated:
 *  - Animated element carries `motion-reduce:transition-none` on the transition class.
 *  - No hardcoded color/spacing/motion values — all via token classes.
 */
export interface TokenSwatchProps {
  /** Which token group to render (used in tests to scope assertions). */
  group: 'surfaces' | 'text' | 'status' | 'motion'
}

export function TokenSwatch({ group }: TokenSwatchProps) {
  if (group === 'surfaces') {
    return (
      <div data-testid="swatch-surfaces">
        <div
          data-testid="surface-base"
          className="bg-surface-base p-4"
        />
        <div
          data-testid="surface-raised"
          className="bg-surface-raised p-4"
        />
        <div
          data-testid="surface-overlay"
          className="bg-surface-overlay p-4"
        />
      </div>
    )
  }

  if (group === 'text') {
    return (
      <div data-testid="swatch-text">
        <span data-testid="text-primary" className="text-text-primary">
          Primary text
        </span>
        <span data-testid="text-secondary" className="text-text-secondary">
          Secondary text
        </span>
        <span data-testid="text-muted" className="text-text-muted">
          Muted text
        </span>
        <span data-testid="text-brand" className="text-primary">
          Brand primary
        </span>
      </div>
    )
  }

  if (group === 'status') {
    return (
      <div data-testid="swatch-status">
        <span data-testid="status-healthy" className="text-status-healthy">
          Healthy
        </span>
        <span data-testid="status-warning" className="text-status-warning">
          Warning
        </span>
        <span data-testid="status-critical" className="text-status-critical">
          Critical
        </span>
        <span data-testid="status-muted" className="text-status-muted">
          Muted
        </span>
      </div>
    )
  }

  if (group === 'motion') {
    /*
     * FR51 / NFR22: animated elements MUST carry `motion-reduce:transition-none`
     * (or the equivalent `motion-reduce:` utility) on every transition class.
     * This element is the canonical reference for that pattern.
     */
    return (
      <div
        data-testid="swatch-motion"
        className="transition-all ease-in-out motion-reduce:transition-none bg-surface-raised p-4"
      >
        Sidebar-style transition element
      </div>
    )
  }

  return null
}
