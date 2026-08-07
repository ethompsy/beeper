/**
 * useAutoRefresh.test.ts
 *
 * Task 5.2 [T] coverage for the auto-refresh polling hook
 * (`src/lib/hooks/useAutoRefresh.ts`): fires `onTick` on the configured
 * interval, pauses while the tab is hidden, resumes on visibility, and
 * cleans up its interval/listener on unmount. Uses Vitest fake timers
 * (`vi.useFakeTimers()`) — this suite owns that setup/teardown locally so
 * it doesn't leak into other test files' real-timer expectations (e.g.
 * `userEvent`'s default delays elsewhere in the suite).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useAutoRefresh } from '../hooks/useAutoRefresh'

/** jsdom's `document.hidden` has no setter by default — override it like the
 * existing `window.scrollY` test-stub pattern in `InvestigationListPage.test.tsx`. */
function setDocumentHidden(hidden: boolean) {
  Object.defineProperty(document, 'hidden', { value: hidden, writable: true, configurable: true })
}

beforeEach(() => {
  vi.useFakeTimers()
  setDocumentHidden(false)
})

afterEach(() => {
  vi.useRealTimers()
  setDocumentHidden(false)
})

describe('useAutoRefresh — fires on the configured interval', () => {
  it('calls onTick every intervalMs while mounted', () => {
    const onTick = vi.fn()
    renderHook(() => useAutoRefresh(onTick, { intervalMs: 5000 }))

    expect(onTick).not.toHaveBeenCalled()

    vi.advanceTimersByTime(5000)
    expect(onTick).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(5000)
    expect(onTick).toHaveBeenCalledTimes(2)

    vi.advanceTimersByTime(15000)
    expect(onTick).toHaveBeenCalledTimes(5)
  })

  it('does not schedule an interval when enabled is false', () => {
    const onTick = vi.fn()
    renderHook(() => useAutoRefresh(onTick, { intervalMs: 5000, enabled: false }))

    vi.advanceTimersByTime(20000)
    expect(onTick).not.toHaveBeenCalled()
  })

  it('always calls the latest onTick closure, not a stale one from the first render', () => {
    const first = vi.fn()
    const second = vi.fn()
    const { rerender } = renderHook(({ cb }) => useAutoRefresh(cb, { intervalMs: 5000 }), {
      initialProps: { cb: first },
    })

    rerender({ cb: second })
    vi.advanceTimersByTime(5000)

    expect(first).not.toHaveBeenCalled()
    expect(second).toHaveBeenCalledTimes(1)
  })

  it('clears its interval on unmount — no further onTick calls after unmounting', () => {
    const onTick = vi.fn()
    const { unmount } = renderHook(() => useAutoRefresh(onTick, { intervalMs: 5000 }))

    vi.advanceTimersByTime(5000)
    expect(onTick).toHaveBeenCalledTimes(1)

    unmount()
    vi.advanceTimersByTime(20000)
    expect(onTick).toHaveBeenCalledTimes(1)
  })
})

describe('useAutoRefresh — pauses while the tab is hidden', () => {
  it('does not fire onTick while document.hidden is true', () => {
    setDocumentHidden(true)
    const onTick = vi.fn()
    renderHook(() => useAutoRefresh(onTick, { intervalMs: 5000 }))

    vi.advanceTimersByTime(20000)
    expect(onTick).not.toHaveBeenCalled()
  })

  it('stops firing once the tab becomes hidden mid-session', () => {
    const onTick = vi.fn()
    renderHook(() => useAutoRefresh(onTick, { intervalMs: 5000 }))

    vi.advanceTimersByTime(5000)
    expect(onTick).toHaveBeenCalledTimes(1)

    setDocumentHidden(true)
    document.dispatchEvent(new Event('visibilitychange'))

    vi.advanceTimersByTime(20000)
    // No further calls accumulated while hidden.
    expect(onTick).toHaveBeenCalledTimes(1)
  })

  it('resumes polling from a fresh interval once the tab becomes visible again (no burst of catch-up calls)', () => {
    const onTick = vi.fn()
    renderHook(() => useAutoRefresh(onTick, { intervalMs: 5000 }))

    vi.advanceTimersByTime(5000)
    expect(onTick).toHaveBeenCalledTimes(1)

    setDocumentHidden(true)
    document.dispatchEvent(new Event('visibilitychange'))
    vi.advanceTimersByTime(30000) // well over several missed intervals

    setDocumentHidden(false)
    document.dispatchEvent(new Event('visibilitychange'))

    // Resuming does not immediately fire a backlog of calls.
    expect(onTick).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(5000)
    expect(onTick).toHaveBeenCalledTimes(2)
  })

  it('a hook mounted while already hidden starts polling once visibility is regained', () => {
    setDocumentHidden(true)
    const onTick = vi.fn()
    renderHook(() => useAutoRefresh(onTick, { intervalMs: 5000 }))

    vi.advanceTimersByTime(10000)
    expect(onTick).not.toHaveBeenCalled()

    setDocumentHidden(false)
    document.dispatchEvent(new Event('visibilitychange'))

    vi.advanceTimersByTime(5000)
    expect(onTick).toHaveBeenCalledTimes(1)
  })

  it('removes its visibilitychange listener on unmount', () => {
    const removeSpy = vi.spyOn(document, 'removeEventListener')
    const onTick = vi.fn()
    const { unmount } = renderHook(() => useAutoRefresh(onTick, { intervalMs: 5000 }))

    unmount()

    expect(removeSpy).toHaveBeenCalledWith('visibilitychange', expect.any(Function))
    removeSpy.mockRestore()
  })
})
