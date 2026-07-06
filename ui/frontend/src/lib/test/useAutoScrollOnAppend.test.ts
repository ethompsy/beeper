/**
 * useAutoScrollOnAppend.test.ts (Task 2.6a)
 *
 * Proves the AC: "[T] new events auto-scroll only when the user is within
 * 100px of the timeline bottom; if scrolled up, new steps append WITHOUT
 * auto-scrolling" (UX spec auto-scroll rule).
 *
 * The hook measures "near bottom" via `window.scrollY` / `innerHeight` /
 * `document.documentElement.scrollHeight` (see the hook's doc comment: the
 * app scrolls at the document level, no bounded inner pane) and scrolls the
 * tracked ref into view via `Element.scrollIntoView`. jsdom doesn't lay out
 * real pixels, so these dimensions are stubbed directly on the relevant
 * globals for each scenario.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useAutoScrollOnAppend } from '../hooks/useAutoScrollOnAppend'

function stubViewport(scrollY: number, innerHeight: number, scrollHeight: number): void {
  Object.defineProperty(window, 'scrollY', { value: scrollY, configurable: true })
  Object.defineProperty(window, 'innerHeight', { value: innerHeight, configurable: true })
  Object.defineProperty(document.documentElement, 'scrollHeight', {
    value: scrollHeight,
    configurable: true,
  })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useAutoScrollOnAppend — within 100px of bottom', () => {
  it('scrolls the tracked element into view when a new step arrives while near the bottom', () => {
    // scrollY(0) + innerHeight(800) = 800; scrollHeight(850) → 50px from bottom (<=100).
    stubViewport(0, 800, 850)

    const scrollIntoView = vi.fn()
    const el = { scrollIntoView } as unknown as HTMLElement
    const ref = { current: el }

    const { rerender } = renderHook(({ count }: { count: number }) => useAutoScrollOnAppend(ref, count), {
      initialProps: { count: 3 },
    })

    act(() => rerender({ count: 4 }))

    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'end' })
  })

  it('scrolls when exactly at the 100px threshold (boundary is inclusive)', () => {
    stubViewport(0, 800, 900) // exactly 100px from bottom

    const scrollIntoView = vi.fn()
    const ref = { current: { scrollIntoView } as unknown as HTMLElement }

    const { rerender } = renderHook(({ count }: { count: number }) => useAutoScrollOnAppend(ref, count), {
      initialProps: { count: 1 },
    })
    act(() => rerender({ count: 2 }))

    expect(scrollIntoView).toHaveBeenCalled()
  })
})

describe('useAutoScrollOnAppend — scrolled up (beyond 100px from bottom)', () => {
  it('does NOT scroll when a new step arrives while the user has scrolled up to read earlier evidence', () => {
    // scrollY(0) + innerHeight(800) = 800; scrollHeight(2000) → 1200px from bottom (>100).
    stubViewport(0, 800, 2000)

    const scrollIntoView = vi.fn()
    const ref = { current: { scrollIntoView } as unknown as HTMLElement }

    const { rerender } = renderHook(({ count }: { count: number }) => useAutoScrollOnAppend(ref, count), {
      initialProps: { count: 3 },
    })

    act(() => rerender({ count: 4 }))

    expect(scrollIntoView).not.toHaveBeenCalled()
  })
})

describe('useAutoScrollOnAppend — no-op cases', () => {
  it('does not scroll when the item count is unchanged', () => {
    stubViewport(0, 800, 850)
    const scrollIntoView = vi.fn()
    const ref = { current: { scrollIntoView } as unknown as HTMLElement }

    const { rerender } = renderHook(({ count }: { count: number }) => useAutoScrollOnAppend(ref, count), {
      initialProps: { count: 3 },
    })
    act(() => rerender({ count: 3 }))

    expect(scrollIntoView).not.toHaveBeenCalled()
  })

  it('does not scroll when the item count shrinks', () => {
    stubViewport(0, 800, 850)
    const scrollIntoView = vi.fn()
    const ref = { current: { scrollIntoView } as unknown as HTMLElement }

    const { rerender } = renderHook(({ count }: { count: number }) => useAutoScrollOnAppend(ref, count), {
      initialProps: { count: 4 },
    })
    act(() => rerender({ count: 3 }))

    expect(scrollIntoView).not.toHaveBeenCalled()
  })
})
