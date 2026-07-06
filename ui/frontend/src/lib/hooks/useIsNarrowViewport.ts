import { useEffect, useState } from 'react'

/**
 * useIsNarrowViewport — viewport-driven breakpoint tracker at the shared
 * `--breakpoint-lg` (1200px) design token
 * (docs/specs/ux-design-specification.md "Responsive without mobile":
 * 768px–1920px+ target, sidebar/KB-panel behavior adapts at 1200px).
 *
 * Extracted from the same `matchMedia` pattern `useSidebarState` uses
 * (`src/lib/hooks/useSidebarState.ts`) so any component needing this exact
 * breakpoint — the Task 2.5 `RelatedKbPanel` anchored-bar-vs-inline-stack
 * behavior (FR26) is the first consumer — doesn't re-implement viewport
 * tracking or risk drifting from the sidebar's breakpoint value.
 */
const LG_BREAKPOINT_PX = 1200

function getIsNarrowViewport(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return !window.matchMedia(`(min-width: ${LG_BREAKPOINT_PX}px)`).matches
}

export function useIsNarrowViewport(): boolean {
  const [isNarrowViewport, setIsNarrowViewport] = useState(getIsNarrowViewport)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const mql = window.matchMedia(`(min-width: ${LG_BREAKPOINT_PX}px)`)
    const handleChange = (): void => setIsNarrowViewport(!mql.matches)
    handleChange()
    mql.addEventListener('change', handleChange)
    return () => mql.removeEventListener('change', handleChange)
  }, [])

  return isNarrowViewport
}
