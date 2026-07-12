/**
 * useStepAnchorScroll.test.ts (Task 3.2, FR53)
 *
 * Unit-level coverage for the hook in isolation — the render-level proof
 * that a real cold `/investigations/<id>#step-<order>` load anchors to the
 * right `InvestigationStep` DOM node lives in
 * `src/routes/test/InvestigationDetailPage.test.tsx` (Task 3.2 describe
 * block), and the real-browser cold-load proof lives in
 * `e2e/detail-permalink.spec.ts`.
 *
 * `Element.prototype.scrollIntoView` is spied per test (the global setup
 * stub in `src/test/setup.ts` already makes it a callable no-op — jsdom has
 * no native implementation — so `vi.spyOn` can attach to it).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useStepAnchorScroll } from '../hooks/useStepAnchorScroll'

function appendStepEl(id: string): HTMLElement {
  const el = document.createElement('li')
  el.id = id
  document.body.appendChild(el)
  return el
}

afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

describe('useStepAnchorScroll — no-op cases', () => {
  it('does nothing when the hash is empty', () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView')
    appendStepEl('step-1')

    renderHook(() => useStepAnchorScroll('', 1))

    expect(scrollIntoView).not.toHaveBeenCalled()
  })

  it('does nothing when the hash does not match any rendered step (stale/bad anchor)', () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView')
    appendStepEl('step-1')

    renderHook(() => useStepAnchorScroll('#step-999', 1))

    expect(scrollIntoView).not.toHaveBeenCalled()
  })
})

describe('useStepAnchorScroll — cold-load anchoring', () => {
  it('scrolls the matching step into view when it already exists on first render', () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => {})
    const target = appendStepEl('step-3')
    appendStepEl('step-1')

    renderHook(() => useStepAnchorScroll('#step-3', 4))

    expect(scrollIntoView).toHaveBeenCalledTimes(1)
    expect(scrollIntoView.mock.instances[0]).toBe(target)
  })

  it('retries once the target step renders asynchronously (steps arrive after the initial fetch)', () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => {})

    // First render: steps haven't arrived yet (stepCount 0), target doesn't exist.
    const { rerender } = renderHook(({ stepCount }) => useStepAnchorScroll('#step-2', stepCount), {
      initialProps: { stepCount: 0 },
    })
    expect(scrollIntoView).not.toHaveBeenCalled()

    // The fetch resolves and steps render — the target now exists.
    const target = appendStepEl('step-2')
    rerender({ stepCount: 2 })

    expect(scrollIntoView).toHaveBeenCalledTimes(1)
    expect(scrollIntoView.mock.instances[0]).toBe(target)
  })

  it('does not re-scroll on a later stepCount change once the hash has already been handled', () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => {})
    appendStepEl('step-1')

    const { rerender } = renderHook(({ stepCount }) => useStepAnchorScroll('#step-1', stepCount), {
      initialProps: { stepCount: 1 },
    })
    expect(scrollIntoView).toHaveBeenCalledTimes(1)

    // A live SSE step append later changes stepCount again — must not re-scroll
    // the page out from under a user who has since scrolled elsewhere.
    appendStepEl('step-2')
    rerender({ stepCount: 2 })

    expect(scrollIntoView).toHaveBeenCalledTimes(1)
  })

  it('re-scrolls when the hash itself changes to a different step', () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => {})
    const first = appendStepEl('step-1')
    const second = appendStepEl('step-2')

    const { rerender } = renderHook(({ hash }) => useStepAnchorScroll(hash, 2), {
      initialProps: { hash: '#step-1' },
    })
    expect(scrollIntoView.mock.instances[0]).toBe(first)

    rerender({ hash: '#step-2' })

    expect(scrollIntoView).toHaveBeenCalledTimes(2)
    expect(scrollIntoView.mock.instances[1]).toBe(second)
  })
})

describe('useStepAnchorScroll — prefers-reduced-motion', () => {
  it('scrolls instantly (behavior: "auto") when the user prefers reduced motion', () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => {})
    appendStepEl('step-1')
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
    )

    renderHook(() => useStepAnchorScroll('#step-1', 1))

    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'auto', block: 'center' })
    vi.unstubAllGlobals()
  })

  it('smooth-scrolls when the user has no reduced-motion preference', () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => {})
    appendStepEl('step-1')
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
    )

    renderHook(() => useStepAnchorScroll('#step-1', 1))

    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' })
    vi.unstubAllGlobals()
  })
})
