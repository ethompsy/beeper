import '@testing-library/jest-dom'

/**
 * jsdom has no ResizeObserver implementation. Radix primitives that measure
 * their trigger/content (e.g. `Tooltip`, used by the Task 2.1 `Sidebar`
 * icon-rail tooltips) call it on mount — without a stub, any test that
 * renders them throws an unhandled `ResizeObserver is not defined` error.
 * A no-op stub is sufficient: these tests assert content/attributes, not
 * layout measurements.
 */
if (typeof globalThis.ResizeObserver === 'undefined') {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver
}

/**
 * jsdom has no EventSource. The Task 2.6a live-updates hook
 * (`useInvestigationEvents`) opens one on mount via its default factory, so
 * any test that renders `InvestigationDetailPage` throws
 * `EventSource is not defined` without this stub. A no-op stub (never fires
 * open/message/error) is sufficient: page-level tests assert the initial
 * one-shot-fetch render, while the hook's own tests inject a mock factory to
 * drive the lifecycle. Matches the ResizeObserver stub pattern above.
 */
if (typeof globalThis.EventSource === 'undefined') {
  class EventSourceStub {
    static readonly CONNECTING = 0
    static readonly OPEN = 1
    static readonly CLOSED = 2
    readonly CONNECTING = 0
    readonly OPEN = 1
    readonly CLOSED = 2
    readyState = 0
    url: string
    withCredentials = false
    onopen: ((this: EventSource, ev: Event) => unknown) | null = null
    onmessage: ((this: EventSource, ev: MessageEvent) => unknown) | null = null
    onerror: ((this: EventSource, ev: Event) => unknown) | null = null
    constructor(url: string | URL) {
      this.url = String(url)
    }
    addEventListener() {}
    removeEventListener() {}
    dispatchEvent() {
      return false
    }
    close() {
      this.readyState = 2
    }
  }
  globalThis.EventSource = EventSourceStub as unknown as typeof EventSource
}

/**
 * jsdom does not implement Element.prototype.scrollIntoView. The Task 2.6a
 * auto-scroll-on-append behavior calls it when new live steps arrive, which
 * throws in tests that render the detail timeline. A no-op stub is sufficient:
 * the auto-scroll *decision* logic is unit-tested directly in
 * `useAutoScrollOnAppend.test.ts`; page tests only need the call not to throw.
 */
if (typeof Element !== 'undefined' && typeof Element.prototype.scrollIntoView !== 'function') {
  Element.prototype.scrollIntoView = function scrollIntoView() {}
}
