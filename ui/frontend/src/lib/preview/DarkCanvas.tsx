import type { CSSProperties, ReactNode } from 'react'

/**
 * DarkCanvas — preview-only wrapper for design-sync (`cfg.provider`).
 *
 * Beeper is a dark-first design system: in the app, `tokens.css`'s
 * `@layer base` body rule paints `--color-surface-base` behind everything,
 * and Storybook mirrors it via the backgrounds addon (`#0f0f1a` default in
 * `.storybook/preview.ts`). The design-sync preview harness renders on its
 * own white body, and its unlayered body style beats our layered base rule —
 * so this wrapper reproduces the app's real canvas (background, text color,
 * type) around every synced preview. Values are token `var()` references,
 * never literals, so the canvas follows the tokens.
 *
 * NOT part of the component library: intentionally not exported from the
 * `src/lib/index.ts` barrel (no story, no card). It reaches the sync bundle
 * via `cfg.extraEntries` solely so `cfg.provider` can name it.
 */
const canvas: CSSProperties = {
  minHeight: '100vh',
  margin: 0,
  // No padding: position:fixed components (AppShell, Sidebar) anchor to the
  // viewport — canvas padding would displace flow content against them.
  padding: 0,
  backgroundColor: 'var(--color-surface-base)',
  color: 'var(--color-text-primary)',
  fontFamily: 'var(--font-sans)',
  fontSize: 'var(--text-base-size)',
  lineHeight: 'var(--text-base-lh)',
  WebkitFontSmoothing: 'antialiased',
} as CSSProperties

export function DarkCanvas({ children }: { children?: ReactNode }) {
  return <div style={canvas}>{children}</div>
}
