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
