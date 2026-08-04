import { useEffect, useRef } from 'react'

/**
 * useStepAnchorScroll — the FR53 detail-permalink step anchor (Task 3.2).
 *
 * FR53: "Investigation detail: the investigation id (path) and the anchored
 * step (`#step-<id>`), so a shared link lands on the step under discussion."
 * The hash is *content* navigation state (shareable), not ephemeral chrome —
 * unlike sidebar collapsed/expanded state or a pixel scroll offset (FR53's
 * explicit carve-out), so it lives in the URL hash rather than component
 * state, and this hook's only job is to make a cold load *act* on it.
 *
 * Each rendered `InvestigationStep` carries `id="step-<order>"` (see
 * `InvestigationDetailPage.tsx`) — `order` rather than `key`/`id` because
 * it is the one field guaranteed present on every step DTO (`key` can be
 * `null`; see `src/api/investigation-detail.ts`) and is already the
 * identity every merge helper (`mergeLiveStepEvents`, `mergeBackfilledSteps`)
 * keys off of. A `#step-<order>` hash therefore always matches a real
 * element id whenever `order` matches a step that has actually rendered.
 *
 * ── Async timing (steps arrive after the initial fetch resolves) ──
 *
 * On a cold load the summary header paints synchronously (Task 2.5), but
 * the steps list is empty until `useInvestigationDetail`'s fetch resolves.
 * This hook re-runs whenever `stepCount` changes (the caller passes the
 * merged/rendered step list's length) so it retries the DOM lookup each
 * time more steps render, rather than only once on mount when the target
 * element doesn't exist yet. Once the target is found, it is remembered
 * (`handledHashRef`) so later step arrivals (e.g. a live SSE append) don't
 * keep re-scrolling the page out from under a user who has since scrolled
 * elsewhere. A hash that never matches any rendered step (bad/stale link)
 * is a silent no-op — never an error state.
 *
 * ── Interaction with header focus (Task 2.1 `useRouteFocusManagement`) ──
 *
 * `useRouteFocusManagement` focuses `#detail-summary-heading` with
 * `{ preventScroll: true }` on every detail-route entry, including this
 * same cold load, and it does so as soon as the header paints — before the
 * fetch that populates the steps list even resolves. This hook never
 * competes for focus (it only calls `scrollIntoView`, never `.focus()`), so
 * the header keeps WCAG 2.4.3 focus ownership on load; this hook settles
 * the *scroll position* afterward, once the anchored step exists. Because
 * the header's focus call passes `preventScroll: true`, it can never undo
 * this hook's scroll either, regardless of effect ordering — the two
 * behaviors are non-competing by construction, not just by luck of timing.
 *
 * `prefers-reduced-motion`: scrolls instantly (`behavior: 'auto'`) rather
 * than smooth-scrolling, matching the reduced-motion bar the rest of the
 * detail view holds itself to (NFR22/FR51).
 */
export function useStepAnchorScroll(hash: string, stepCount: number): void {
  const handledHashRef = useRef<string | null>(null)

  useEffect(() => {
    if (hash === '') return
    if (handledHashRef.current === hash) return // already scrolled for this exact hash

    const targetId = hash.slice(1) // hash is "#step-<order>"; element id has no leading '#'
    if (targetId === '') return

    const target = document.getElementById(targetId)
    if (target == null) return // step hasn't rendered yet (or the anchor is stale) — retry next stepCount change

    handledHashRef.current = hash

    const prefersReducedMotion =
      typeof window !== 'undefined' && typeof window.matchMedia === 'function'
        ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
        : false

    target.scrollIntoView({ behavior: prefersReducedMotion ? 'auto' : 'smooth', block: 'center' })
    // `stepCount` is a re-run trigger only — the effect reads the live DOM
    // via `document.getElementById`, not `stepCount` itself, so each time
    // more steps render this re-checks whether the target now exists.
  }, [hash, stepCount])
}
