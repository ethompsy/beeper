/**
 * useIsNarrowViewport.test.ts (Task 2.5) — the shared 1200px breakpoint
 * tracker consumed by the `RelatedKbPanel` anchored-bar-vs-inline
 * responsive behavior (FR26). Mocking strategy mirrors
 * `useSidebarState.test.ts`'s `matchMedia` mock exactly, since this hook
 * was extracted from the same pattern.
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useIsNarrowViewport } from '../hooks/useIsNarrowViewport'

function installMatchMedia(initialMatches: boolean) {
  let matches = initialMatches
  const listeners = new Set<() => void>()

  const mql = {
    get matches() {
      return matches
    },
    media: '(min-width: 1200px)',
    addEventListener: (_event: string, listener: () => void) => {
      listeners.add(listener)
    },
    removeEventListener: (_event: string, listener: () => void) => {
      listeners.delete(listener)
    },
  }

  window.matchMedia = vi.fn().mockReturnValue(mql) as unknown as typeof window.matchMedia

  return {
    setMatches(next: boolean) {
      matches = next
      act(() => {
        listeners.forEach((listener) => listener())
      })
    },
  }
}

describe('useIsNarrowViewport', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns false when the viewport matches >=1200px', () => {
    installMatchMedia(true) // matches "(min-width: 1200px)"
    const { result } = renderHook(() => useIsNarrowViewport())
    expect(result.current).toBe(false)
  })

  it('returns true when the viewport does not match >=1200px', () => {
    installMatchMedia(false)
    const { result } = renderHook(() => useIsNarrowViewport())
    expect(result.current).toBe(true)
  })

  it('updates live on a matchMedia change event (viewport resize)', () => {
    const { setMatches } = installMatchMedia(true)
    const { result } = renderHook(() => useIsNarrowViewport())
    expect(result.current).toBe(false)

    setMatches(false)
    expect(result.current).toBe(true)
  })
})
