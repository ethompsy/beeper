/**
 * useSidebarState.test.ts
 *
 * AC [T] (Task 2.1) — the sidebar state-machine logic:
 *   - Collapsed = icon rail; ≥1200px expand pushes, <1200px expand overlays
 *     (no width shift); detail route auto-collapses regardless of viewport
 *     (FR41/42/44).
 *
 * Strategy: mock `window.matchMedia` to simulate wide/narrow viewports and
 * drive the hook directly with `renderHook` — this proves the state
 * machine's decision logic in isolation from any rendered DOM/CSS, which is
 * covered separately by the AppShell/Sidebar class-assertion tests.
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useSidebarState } from '../hooks/useSidebarState'

/** Minimal MediaQueryList mock supporting matches + change listeners. */
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

describe('useSidebarState', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('auto mode (route-driven default)', () => {
    it('is expanded by default at >=1200px viewport', () => {
      installMatchMedia(true)
      const { result } = renderHook(() => useSidebarState('auto', 'route-a'))
      expect(result.current.expanded).toBe(true)
      expect(result.current.isNarrowViewport).toBe(false)
      expect(result.current.isOverlay).toBe(false)
    })

    it('is collapsed (icon rail) by default at <1200px viewport', () => {
      installMatchMedia(false)
      const { result } = renderHook(() => useSidebarState('auto', 'route-a'))
      expect(result.current.expanded).toBe(false)
      expect(result.current.isNarrowViewport).toBe(true)
    })

    it('manual expand at >=1200px pushes content (isOverlay = false)', () => {
      installMatchMedia(true)
      const { result } = renderHook(() => useSidebarState('auto', 'route-a'))

      // Already expanded by default at this width — toggle collapses then
      // toggle again to prove manual expand explicitly.
      act(() => result.current.toggle())
      expect(result.current.expanded).toBe(false)
      act(() => result.current.toggle())
      expect(result.current.expanded).toBe(true)
      expect(result.current.isOverlay).toBe(false)
    })

    it('manual expand at <1200px overlays content (isOverlay = true, no width shift)', () => {
      installMatchMedia(false)
      const { result } = renderHook(() => useSidebarState('auto', 'route-a'))

      expect(result.current.expanded).toBe(false)
      act(() => result.current.toggle())
      expect(result.current.expanded).toBe(true)
      expect(result.current.isOverlay).toBe(true)
    })

    it('manual collapse at <1200px is not an overlay', () => {
      installMatchMedia(false)
      const { result } = renderHook(() => useSidebarState('auto', 'route-a'))
      expect(result.current.expanded).toBe(false)
      expect(result.current.isOverlay).toBe(false)
    })

    it('responds live to a viewport resize (matchMedia change event)', () => {
      const media = installMatchMedia(true)
      const { result } = renderHook(() => useSidebarState('auto', 'route-a'))
      expect(result.current.expanded).toBe(true)

      media.setMatches(false)
      expect(result.current.isNarrowViewport).toBe(true)
      expect(result.current.expanded).toBe(false)
    })
  })

  describe('collapsed mode (route-driven, FR44)', () => {
    it('forces collapsed regardless of a wide viewport', () => {
      installMatchMedia(true)
      const { result } = renderHook(() => useSidebarState('collapsed', 'detail-route'))
      expect(result.current.expanded).toBe(false)
      expect(result.current.isOverlay).toBe(false)
    })

    it('forces collapsed regardless of a narrow viewport', () => {
      installMatchMedia(false)
      const { result } = renderHook(() => useSidebarState('collapsed', 'detail-route'))
      expect(result.current.expanded).toBe(false)
    })

    it('a prior manual expand does not defeat the route-driven collapse', () => {
      installMatchMedia(true)
      const { result, rerender } = renderHook(
        ({ mode, key }: { mode: 'auto' | 'collapsed'; key: string }) => useSidebarState(mode, key),
        { initialProps: { mode: 'auto' as const, key: 'list-route' } },
      )
      expect(result.current.expanded).toBe(true)

      rerender({ mode: 'collapsed', key: 'detail-route' })
      expect(result.current.expanded).toBe(false)
    })

    it('the user can still manually re-expand while on the detail route (FR44 final clause)', () => {
      installMatchMedia(true)
      const { result } = renderHook(() => useSidebarState('collapsed', 'detail-route'))
      expect(result.current.expanded).toBe(false)

      act(() => result.current.toggle())
      expect(result.current.expanded).toBe(true)

      // Toggling again re-collapses it — the override is a real toggle,
      // not a one-way escape hatch.
      act(() => result.current.toggle())
      expect(result.current.expanded).toBe(false)
    })
  })

  describe('manual override scoping (spec: "until next route change")', () => {
    it('clears the manual override when routeKey changes', () => {
      installMatchMedia(false)
      const { result, rerender } = renderHook(
        ({ key }: { key: string }) => useSidebarState('auto', key),
        { initialProps: { key: 'route-a' } },
      )

      act(() => result.current.toggle())
      expect(result.current.expanded).toBe(true)

      rerender({ key: 'route-b' })
      // Back to the viewport-appropriate default (collapsed at <1200px) —
      // the manual override from route-a does not leak into route-b.
      expect(result.current.expanded).toBe(false)
    })
  })

  describe('`[` keyboard shortcut', () => {
    it('toggles the sidebar', () => {
      installMatchMedia(true)
      const { result } = renderHook(() => useSidebarState('auto', 'route-a'))
      expect(result.current.expanded).toBe(true)

      act(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: '[' }))
      })
      expect(result.current.expanded).toBe(false)
    })

    it('is ignored while focus is inside a text input', () => {
      installMatchMedia(true)
      const { result } = renderHook(() => useSidebarState('auto', 'route-a'))
      expect(result.current.expanded).toBe(true)

      const input = document.createElement('input')
      document.body.appendChild(input)
      input.focus()

      act(() => {
        input.dispatchEvent(new KeyboardEvent('keydown', { key: '[', bubbles: true }))
      })
      expect(result.current.expanded).toBe(true)

      document.body.removeChild(input)
    })
  })
})
