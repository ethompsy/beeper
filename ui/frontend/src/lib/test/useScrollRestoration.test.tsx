/**
 * useScrollRestoration.test.tsx
 *
 * Task 2.2 AC [T] — "returning to the list from a detail route restores the
 * previous list scroll position" (FR22). Tests the hook in isolation with a
 * minimal mount/unmount harness rather than the full page, so the
 * save-on-unmount / restore-on-ready contract is unambiguous.
 *
 * `ready` gating: the hook only restores once `ready` is true (see the
 * hook's doc comment — restoring against a not-yet-loaded/short page would
 * silently clamp `window.scrollTo` to a smaller offset than the saved one).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { useScrollRestoration } from '../hooks/useScrollRestoration'

function Harness({ scrollKey, ready }: { scrollKey: string; ready: boolean }) {
  useScrollRestoration(scrollKey, ready)
  return <div>harness</div>
}

beforeEach(() => {
  sessionStorage.clear()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('useScrollRestoration', () => {
  it('restores window.scrollTo(0, saved) once ready=true and a saved position exists', () => {
    sessionStorage.setItem('beeper:list-scroll:/investigations', '180')
    const scrollToSpy = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})

    render(<Harness scrollKey="/investigations" ready={true} />)

    expect(scrollToSpy).toHaveBeenCalledWith(0, 180)
  })

  it('does NOT restore while ready=false (still loading)', () => {
    sessionStorage.setItem('beeper:list-scroll:/investigations', '180')
    const scrollToSpy = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})

    render(<Harness scrollKey="/investigations" ready={false} />)

    expect(scrollToSpy).not.toHaveBeenCalled()
  })

  it('restores once ready flips from false to true (loading -> loaded transition)', () => {
    sessionStorage.setItem('beeper:list-scroll:/investigations', '450')
    const scrollToSpy = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})

    const { rerender } = render(<Harness scrollKey="/investigations" ready={false} />)
    expect(scrollToSpy).not.toHaveBeenCalled()

    rerender(<Harness scrollKey="/investigations" ready={true} />)
    expect(scrollToSpy).toHaveBeenCalledWith(0, 450)
  })

  it('only restores once even if ready stays true across re-renders (does not fight user scrolling)', () => {
    sessionStorage.setItem('beeper:list-scroll:/investigations', '100')
    const scrollToSpy = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})

    const { rerender } = render(<Harness scrollKey="/investigations" ready={true} />)
    rerender(<Harness scrollKey="/investigations" ready={true} />)
    rerender(<Harness scrollKey="/investigations" ready={true} />)

    expect(scrollToSpy).toHaveBeenCalledTimes(1)
  })

  it('does not call scrollTo when there is no saved position', () => {
    const scrollToSpy = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})

    render(<Harness scrollKey="/investigations" ready={true} />)

    expect(scrollToSpy).not.toHaveBeenCalled()
  })

  it('saves the last-observed window.scrollY to sessionStorage on unmount', () => {
    const { unmount } = render(<Harness scrollKey="/investigations" ready={true} />)

    Object.defineProperty(window, 'scrollY', { value: 320, writable: true, configurable: true })
    window.dispatchEvent(new Event('scroll'))
    unmount()

    expect(sessionStorage.getItem('beeper:list-scroll:/investigations')).toBe('320')
  })

  it('keys the saved position independently per `key`', () => {
    const { unmount: unmountA } = render(<Harness scrollKey="/investigations" ready={true} />)
    Object.defineProperty(window, 'scrollY', { value: 50, writable: true, configurable: true })
    window.dispatchEvent(new Event('scroll'))
    unmountA()

    const { unmount: unmountB } = render(<Harness scrollKey="/other-list" ready={true} />)
    Object.defineProperty(window, 'scrollY', { value: 999, writable: true, configurable: true })
    window.dispatchEvent(new Event('scroll'))
    unmountB()

    expect(sessionStorage.getItem('beeper:list-scroll:/investigations')).toBe('50')
    expect(sessionStorage.getItem('beeper:list-scroll:/other-list')).toBe('999')
  })
})
