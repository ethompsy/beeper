import { test, expect, type Page } from '@playwright/test'

/**
 * permalink-integrity.spec.ts
 *
 * Task 3.4 AC [T] — the NFR24/FR53 integrity gate: proves the session's
 * headline requirement holistically — "copy any triage URL, open it cold,
 * and get the identical view" — rather than re-testing either permalink
 * mechanism (Task 3.1's `?status=` list filter, Task 3.2's `#step-<order>`
 * detail anchor) in isolation. Both mechanisms already have their own
 * per-task e2e coverage (`investigation-list.spec.ts`, `detail-permalink.spec.ts`);
 * this spec is deliberately a NEW file (per the Task 3.4 scope note) so it
 * doesn't collide with the parallel Task 3.3 chrome-boundary spec, and it
 * does NOT re-implement that negative chrome-boundary test.
 *
 * Every test here is a genuine cold load: a fresh `page.goto` straight to
 * the permalink URL, no prior in-app navigation/click establishing state —
 * matching how a teammate actually experiences a pasted link (a new
 * browser tab, not a continuation of an existing SPA session).
 *
 * Runs against the *built* app (`vite preview`, matching the existing e2e
 * convention) — no Flask backend, so the API is mocked via `page.route`,
 * reusing the mock-shape helpers already established in
 * `investigation-list.spec.ts` / `detail-permalink.spec.ts`.
 */

interface MockInvestigation {
  id: string
  status: 'investigating' | 'awaiting_confirmation' | 'completed' | 'failed'
  service: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  condition: string
  started_at: string | null
  triggered_at: string | null
  completed_at: string | null
  workflow_state: 'detected' | 'investigating' | 'resolved' | 'verified' | 'failed' | null
  workflow_state_changed_at: string | null
}

function makeInvestigation(overrides: Partial<MockInvestigation>): MockInvestigation {
  return {
    id: 'inv-default',
    status: 'investigating',
    service: 'checkout-service',
    severity: 'medium',
    condition: 'elevated error rate',
    started_at: new Date().toISOString(),
    triggered_at: new Date().toISOString(),
    completed_at: null,
    workflow_state: 'investigating',
    workflow_state_changed_at: null,
    ...overrides,
  }
}

async function mockInvestigationsListApi(page: Page, data: MockInvestigation[]): Promise<void> {
  await page.route('**/api/v1/investigations/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
  })
}

interface MockStep {
  order: number
  key: string | null
  label: string | null
  state: 'completed' | 'active' | 'pending' | 'error'
  type: 'metric' | 'log' | 'deploy' | 'kb' | 'correlation' | 'summary'
}

function makeCompletedSteps(count: number): MockStep[] {
  return Array.from({ length: count }, (_, i) => ({
    order: i + 1,
    key: `step-key-${i + 1}`,
    // Padded so `count` steps overflow a constrained viewport, forcing real
    // scrolling — same technique as `detail-permalink.spec.ts`.
    label: `Step ${i + 1} of ${count} — root-caused checkout-service latency to a bad deploy`,
    state: 'completed',
    type: 'log',
  }))
}

/**
 * Mocks a single COMPLETED investigation's one-shot detail fetch. Scoped to
 * the bare `.../investigations/<id>` path (no trailing segment) so it does
 * NOT intercept the separate `.../investigations/<id>/events` SSE endpoint
 * (Task 2.6a) — that stream is left to fail/degrade on its own against the
 * backend-less preview server, matching `detail-permalink.spec.ts`.
 */
async function mockCompletedDetailApi(page: Page, investigationId: string, steps: MockStep[]): Promise<void> {
  await page.route(`**/api/v1/investigations/${investigationId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: investigationId,
        status: 'completed',
        service: 'checkout-service',
        message: null,
        metadata: {
          id: investigationId,
          status: 'completed',
          service: 'checkout-service',
          severity: 'High',
          condition: 'HTTP 5xx error rate elevated (12%)',
          message: null,
          started_at: '18m ago',
          triggered_at: null,
          completed_at: '2m ago',
          workflow_state: 'resolved',
          workflow_state_changed_at: '2m ago',
          signal_count: 3,
          job_name: 'job-1',
        },
        steps,
      }),
    })
  })
}

test.describe('permalink integrity — filtered-list cold load (Task 3.4, NFR24/FR53)', () => {
  test('cold-loading a filtered-list permalink reproduces the identical filtered/ordered list, including restored scroll position', async ({
    page,
  }) => {
    const completedRows = Array.from({ length: 40 }, (_, i) =>
      makeInvestigation({ id: `completed-${i}`, service: `svc-completed-${i}`, status: 'completed' }),
    )
    await mockInvestigationsListApi(page, [
      makeInvestigation({ id: 'active-1', service: 'svc-active', status: 'investigating' }),
      ...completedRows,
      makeInvestigation({ id: 'failed-1', service: 'svc-failed', status: 'failed' }),
    ])
    // Constrained viewport so 40 resolved rows genuinely overflow it — the
    // scroll-restoration assertion below needs real scroll room (matches
    // the technique in investigation-list.spec.ts's own scroll-restore test).
    await page.setViewportSize({ width: 1280, height: 500 })

    // Seed a saved scroll offset the way `useScrollRestoration` actually
    // persists it — `sessionStorage`, keyed by route pathname only (NOT by
    // query string; see useScrollRestoration.ts) — simulating a teammate
    // who had this exact list route open earlier in this same browser tab,
    // scrolled down, and is now re-opening the copied filtered-list
    // permalink. `addInitScript` runs before any page script on the
    // upcoming navigation, so this is in place before the SPA ever mounts —
    // a genuine cold load, not a simulated in-app scroll.
    await page.addInitScript(() => {
      window.sessionStorage.setItem('beeper:list-scroll:/investigations', '600')
    })

    // The permalink itself: a direct, fresh navigation — no prior in-app
    // filter click, no prior page in this browsing context.
    await page.goto('/app/investigations?status=resolved')

    // Identical FILTER half of NFR24: the Resolved group, and only that
    // group, is showing.
    await expect(page.getByRole('link', { name: /svc-completed-0 investigation/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /svc-active investigation/i })).toHaveCount(0)
    await expect(page.getByRole('link', { name: /svc-failed investigation/i })).toHaveCount(0)
    await expect(page.getByRole('tab', { name: /Resolved/ })).toHaveAttribute('aria-selected', 'true')

    // Identical SCROLL half of NFR24: the saved offset is restored on this
    // very cold load — not just the filter, but "the identical view."
    await expect(async () => {
      const scrollY = await page.evaluate(() => window.scrollY)
      expect(scrollY).toBe(600)
    }).toPass()
  })
})

test.describe('permalink integrity — Completed-investigation detail + step anchor cold load (Task 3.4, NFR24/FR53)', () => {
  test('cold-loading a Completed investigation detail permalink anchored to a step reproduces the identical detail view AND scrolls the anchored step into view', async ({
    page,
  }) => {
    // 3.2's own suite (detail-permalink.spec.ts) only ever mocked
    // status: 'investigating' investigations for its step-anchor cases —
    // this is the follow-up gap this task's AC calls out explicitly: a
    // Completed investigation's step anchor was never exercised.
    await mockCompletedDetailApi(page, 'INV-0099', makeCompletedSteps(20))
    await page.setViewportSize({ width: 1024, height: 600 })

    await page.goto('/app/investigations/INV-0099#step-15')

    // Identical DETAIL-VIEW half of NFR24: the Completed investigation's
    // summary facts render exactly as the one-shot fetch describes them —
    // service, severity, the Completed job-phase badge (not e.g. a stale
    // "Investigating" badge), and the plain-language problem state.
    const heading = page.getByRole('heading', { name: 'checkout-service' })
    await expect(heading).toBeVisible()
    await expect(page.locator('[data-field="severity"]')).toHaveText('High')
    await expect(page.locator('[data-slot="status-badge"]')).toHaveAttribute('data-variant', 'completed')
    await expect(page.locator('[data-slot="status-badge"]')).toHaveText('Completed')

    // Identical STEP-ANCHOR half of NFR24: the anchored step is scrolled
    // into view, exactly as it would be for any other status — this is the
    // combination 3.2's suite never covered.
    const target = page.locator('#step-15')
    await expect(target).toBeVisible()
    await expect(target).toBeInViewport()

    // Sanity check a real scroll actually happened, not a no-op — the far
    // first step is no longer in view (same technique as
    // detail-permalink.spec.ts's equivalent non-completed assertion).
    await expect(page.locator('#step-1')).not.toBeInViewport()

    // The rest of the timeline is intact too — all 20 completed steps
    // rendered, not just the anchored one (the "identical view" is the
    // whole page, not a partial render around the anchor).
    await expect(page.locator('[data-slot="investigation-steps"] [id^="step-"]')).toHaveCount(20)
  })
})
