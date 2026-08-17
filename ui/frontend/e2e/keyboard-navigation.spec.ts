import { test, expect, type Page } from '@playwright/test'

/**
 * keyboard-navigation.spec.ts (Task 5.5)
 *
 * The keyboard/focus half of the Task 5.5 [T] AC ("keyboard nav + visible
 * focus verified, NFR22"), complementing `a11y.spec.ts`'s axe sweep:
 *   1. The `AppShell` skip link (Task 2.1) still works on the newly
 *      migrated Milestone 2.1 routes, not just the original investigations
 *      route it shipped with.
 *   2. Tabbing through each migrated view lands on every interactive
 *      element in a sensible order, and every stop shows a VISIBLE focus
 *      indicator — asserted by reading the focused element's computed
 *      `outline`/`box-shadow` (not just trusting a class name is present).
 *   3. Enter/Space activate keyboard-operable controls that aren't native
 *      `<button>`/`<a>` elements (the Metrics trend-chart data points,
 *      `role="button"` on an SVG `<circle>`) and the status-group-style
 *      filter pattern (investigations `StatusGroupFilter`, regression).
 *   4. The Knowledge Base header's out-of-scope `<a>` links land in a tab
 *      order consistent with their visual position (the Task 5.1 follow-up
 *      this task was asked to verify).
 *
 * Runs against the *built* app (`vite preview`), matching every other e2e
 * spec's convention — each test mocks its view's JSON API via `page.route`.
 */

/** Reads the currently-focused element's accessible name/tag/role — for asserting tab-order sequences without hardcoding brittle CSS selectors. */
async function focusedElementDescriptor(page: Page): Promise<{ tag: string; text: string; role: string | null }> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null
    if (!el) return { tag: 'none', text: '', role: null }
    return {
      tag: el.tagName.toLowerCase(),
      text: (el.textContent ?? el.getAttribute('aria-label') ?? '').trim().slice(0, 60),
      role: el.getAttribute('role'),
    }
  })
}

/**
 * True if the currently-focused element has a browser-rendered visible
 * focus indicator — either a non-`none` `outline` with nonzero width (the
 * `outline-*` utility Tailwind convention, and the browser UA default for
 * plain links/buttons) or a `box-shadow` (the `ring-*` utility convention,
 * box-shadow-based). Reads actual computed style, not class names, so it
 * catches cases where a class is present but doesn't render (e.g. an
 * `outline` utility on an element that doesn't support it).
 */
async function focusedElementHasVisibleIndicator(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null
    if (!el || el === document.body) return false
    const style = window.getComputedStyle(el)
    const hasOutline = style.outlineStyle !== 'none' && parseFloat(style.outlineWidth || '0') > 0
    const hasBoxShadow = style.boxShadow !== 'none' && style.boxShadow.trim() !== ''
    return hasOutline || hasBoxShadow
  })
}

/** Tabs forward `count` times, asserting a visible focus indicator after every stop. Returns the sequence of focused-element descriptors. */
async function tabThroughAndAssertVisibleFocus(
  page: Page,
  count: number,
): Promise<Array<{ tag: string; text: string; role: string | null }>> {
  const sequence: Array<{ tag: string; text: string; role: string | null }> = []
  for (let i = 0; i < count; i++) {
    await page.keyboard.press('Tab')
    const descriptor = await focusedElementDescriptor(page)
    sequence.push(descriptor)
    if (descriptor.tag === 'none') continue // focus left the document (e.g. address bar) — nothing to assert
    const visible = await focusedElementHasVisibleIndicator(page)
    expect(visible, `expected a visible focus indicator on stop ${i + 1}: ${JSON.stringify(descriptor)}`).toBe(true)
  }
  return sequence
}

// ─────────────────────────────────────────────────────────────────────────
// 1. Skip link on the newly migrated routes
// ─────────────────────────────────────────────────────────────────────────

test.describe('skip link on Milestone 2.1 routes (WCAG 2.4.1)', () => {
  test('/app/knowledge — first Tab focuses the skip link, Enter jumps to main content', async ({ page }) => {
    await page.route('**/api/v1/knowledge/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ query: '', entries: [], has_exact_matches: true, error: null }),
      })
    })
    await page.goto('/app/knowledge')

    await page.keyboard.press('Tab')
    const skipLink = page.getByRole('link', { name: 'Skip to main content' })
    await expect(skipLink).toBeFocused()
    await expect(await focusedElementHasVisibleIndicator(page)).toBe(true)

    await page.keyboard.press('Enter')
    await expect(page.locator('#main-content')).toBeFocused()
  })

  test('/app/ingestion-stats — first Tab focuses the skip link, Enter jumps to main content', async ({ page }) => {
    await page.route('**/api/v1/ingestion/stats', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          buffer_size: 1,
          buffered_count: 0,
          dropped_count: 0,
          is_full: false,
          metrics_received: 0,
          logs_received: 0,
          anomalies_detected: 0,
          anomalies_suppressed: 0,
          active_metric_detectors: 0,
          ewma_warmup_samples: 0,
          ewma_warmup_minimum: 100,
        }),
      })
    })
    await page.goto('/app/ingestion-stats')

    await page.keyboard.press('Tab')
    await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused()

    await page.keyboard.press('Enter')
    await expect(page.locator('#main-content')).toBeFocused()
  })
})

// ─────────────────────────────────────────────────────────────────────────
// 2. Visible focus indicator — Tab through every migrated view
// ─────────────────────────────────────────────────────────────────────────

test.describe('visible focus indicator while tabbing through each migrated view', () => {
  test('Knowledge Base browse view', async ({ page }) => {
    await page.route('**/api/v1/knowledge/**', async (route) => {
      const url = new URL(route.request().url())
      if (!url.pathname.endsWith('/api/v1/knowledge/') && !url.pathname.endsWith('/api/v1/knowledge')) {
        return route.fallback()
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          query: '',
          entries: [
            {
              id: 'p1',
              entry_id: 'kb-001',
              entry_type: 'investigation',
              title: 'checkout-service latency after deploy',
              service: 'checkout-service',
              created_at: null,
              updated_at: null,
              author: null,
              version: 1,
              tags: [],
              validation_status: null,
              auto_published: false,
              relevance_score: null,
              snippet: 'snippet text',
            },
          ],
          has_exact_matches: true,
          error: null,
        }),
      })
    })
    await page.goto('/app/knowledge')
    await expect(page.getByRole('link', { name: /checkout-service latency after deploy/i })).toBeVisible()

    // Skip link, sidebar toggle, 6 sidebar nav items = 8 stops before the
    // page's own content; +5 more reaches the 3 header action links, the
    // search box, and the one entry card (13 total).
    const sequence = await tabThroughAndAssertVisibleFocus(page, 13)
    const texts = sequence.map((s) => s.text)
    expect(texts.some((t) => t.includes('Learning Insights'))).toBe(true)
    expect(texts.some((t) => t.includes('Trust Settings'))).toBe(true)
    expect(texts.some((t) => t.includes('Import Runbook'))).toBe(true)
  })

  test('Ingestion Stats view', async ({ page }) => {
    await page.route('**/api/v1/ingestion/stats', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          buffer_size: 1,
          buffered_count: 0,
          dropped_count: 0,
          is_full: false,
          metrics_received: 100,
          logs_received: 50,
          anomalies_detected: 1,
          anomalies_suppressed: 0,
          active_metric_detectors: 2,
          ewma_warmup_samples: 100,
          ewma_warmup_minimum: 100,
        }),
      })
    })
    await page.goto('/app/ingestion-stats')
    await expect(page.getByText('Metrics Received')).toBeVisible()

    // This view has no page-local interactive controls (pure read-only
    // dashboard) — Tab through the shell (skip link + toggle + 6 nav items)
    // and confirm every stop still shows a visible indicator; nothing more
    // to land on afterwards.
    await tabThroughAndAssertVisibleFocus(page, 8)
  })

  test('Sources view', async ({ page }) => {
    await page.route('**/api/v1/sources/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            name: 'prometheus-main',
            type: 'prometheus',
            endpoint: 'http://prometheus:9090',
            status: 'error',
            last_check: null,
            error: { type: 'connection_error', message: 'Connection refused', details: 'trace' },
          },
        ]),
      })
    })
    await page.goto('/app/sources')
    await expect(page.getByText('prometheus-main')).toBeVisible()

    // +1 more stop to reach the "Show technical details" <summary> disclosure.
    const sequence = await tabThroughAndAssertVisibleFocus(page, 9)
    expect(sequence.some((s) => s.text.includes('Show technical details'))).toBe(true)
  })

  test('Spending view', async ({ page }) => {
    await page.route('**/api/v1/spending/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          summary: {
            daily_cost_usd: 1,
            monthly_cost_usd: 1,
            daily_cap_usd: null,
            monthly_cap_usd: null,
            daily_pct: null,
            monthly_pct: null,
            projected_monthly_usd: 1,
            daily_investigation_count: 1,
            monthly_investigation_count: 1,
            rate_per_hour: 1,
            rate_limit: null,
          },
          cap_status: { enforcement_active: false, caps_configured: false, warnings: [] },
          provider_config: {
            provider: null,
            model: null,
            endpoint: null,
            api_key_masked: null,
            api_key_configured: false,
            configured: false,
            daily_cap_usd: null,
            monthly_cap_usd: null,
            rate_limit: null,
          },
          trend: [],
        }),
      })
    })
    await page.goto('/app/spending')
    await expect(page.getByRole('heading', { name: 'LLM Provider Configuration' })).toBeVisible()

    // Read-only dashboard, no configured-provider affordances, no chart
    // (empty trend) — just the shell's own controls.
    await tabThroughAndAssertVisibleFocus(page, 8)
  })

  test('Metrics view — filter selects and the trend chart data point', async ({ page }) => {
    await page.route('**/api/v1/metrics/mttr**', async (route) => {
      if (route.request().url().includes('/mttr/drilldown')) return route.fallback()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          period: 'month',
          service: null,
          severity: null,
          services: ['checkout-service'],
          severities: ['high'],
          trend: [{ period: '2026-01', avg_mttr_seconds: 3600, count: 4, start: '2026-01-01', end: '2026-01-31' }],
          overall_avg_mttr_seconds: 3600,
          total_count: 4,
          improvement_pct: null,
          improving: null,
          by_service: [],
          by_severity: [],
        }),
      })
    })
    await page.goto('/app/metrics')
    await expect(page.getByRole('heading', { name: 'MTTR Trends Dashboard' })).toBeVisible()

    // Skip link + toggle + 6 nav items (8), then Period/Service/Severity
    // selects + 2 export links (5) = 13, +1 more reaches the chart data
    // point (14 total).
    const sequence = await tabThroughAndAssertVisibleFocus(page, 14)
    expect(sequence.some((s) => s.role === 'button' && s.text.includes('2026-01'))).toBe(true)
  })

  test('Knowledge Base entry-detail view', async ({ page }) => {
    await page.route('**/api/v1/knowledge/kb-001', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          entry: {
            id: 'p1',
            entry_id: 'kb-001',
            entry_type: 'runbook',
            title: 'Restarting the payments worker pool',
            service: 'payments-api',
            created_at: null,
            updated_at: null,
            author: null,
            version: 1,
            tags: [],
            validation_status: null,
            auto_published: false,
            relevance_score: null,
            content_html: '<p>Step-by-step recovery procedure.</p>',
            root_cause: null,
            resolution: null,
            affected_services: [],
          },
          related_entries: [],
          source_investigation: null,
          contributing_investigations: [],
        }),
      })
    })
    await page.goto('/app/knowledge/kb-001')
    await expect(page.getByRole('heading', { name: 'Restarting the payments worker pool' })).toBeFocused()

    // A cold detail-route load force-collapses... no — KB detail deliberately
    // does NOT force-collapse the sidebar (Task 5.5 finding, see AppLayout.tsx
    // `isFocusManagedDetailRoute` doc comment) — the heading already has
    // focus from WCAG 2.4.3 route-change management, so the very next Tab
    // continues from there, not from the top of the shell.
    await page.keyboard.press('Tab')
    expect(await focusedElementHasVisibleIndicator(page)).toBe(true)
  })
})

// ─────────────────────────────────────────────────────────────────────────
// 3. Enter/Space activation
// ─────────────────────────────────────────────────────────────────────────

test.describe('Enter/Space activate keyboard-operable controls', () => {
  test('Metrics trend-chart data point: Enter opens the drilldown, Space closes it', async ({ page }) => {
    await page.route('**/api/v1/metrics/mttr**', async (route) => {
      if (route.request().url().includes('/mttr/drilldown')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ period_label: '2026-01-01 to 2026-01-31', investigations: [] }),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          period: 'month',
          service: null,
          severity: null,
          services: [],
          severities: [],
          trend: [{ period: '2026-01', avg_mttr_seconds: 3600, count: 4, start: '2026-01-01', end: '2026-01-31' }],
          overall_avg_mttr_seconds: 3600,
          total_count: 4,
          improvement_pct: null,
          improving: null,
          by_service: [],
          by_severity: [],
        }),
      })
    })
    await page.goto('/app/metrics')

    const point = page.getByRole('button', { name: /2026-01/ })
    await point.focus()
    expect(await focusedElementHasVisibleIndicator(page)).toBe(true)

    await page.keyboard.press('Enter')
    await expect(page.getByTestId('drilldown-panel')).toBeVisible()

    // The same point toggles the drilldown closed — TrendChart's
    // `handleKeyDown` treats Space identically to Enter.
    await point.focus()
    await page.keyboard.press(' ')
    await expect(page.getByTestId('drilldown-panel')).toHaveCount(0)
  })

  test('investigations StatusGroupFilter tab (regression): Enter selects the group', async ({ page }) => {
    await page.route('**/api/v1/investigations/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'inv-1',
            status: 'completed',
            service: 'checkout-service',
            severity: 'medium',
            condition: 'resolved',
            started_at: new Date().toISOString(),
            triggered_at: null,
            completed_at: new Date().toISOString(),
            workflow_state: 'resolved',
            workflow_state_changed_at: null,
          },
        ]),
      })
    })
    await page.goto('/app/investigations')

    const resolvedTab = page.getByRole('tab', { name: /Resolved/ })
    await resolvedTab.focus()
    expect(await focusedElementHasVisibleIndicator(page)).toBe(true)

    await page.keyboard.press('Enter')
    await expect(resolvedTab).toHaveAttribute('aria-selected', 'true')
  })
})

// ─────────────────────────────────────────────────────────────────────────
// 4. Knowledge Base header link focus-order (Task 5.1 follow-up)
// ─────────────────────────────────────────────────────────────────────────

test.describe('Knowledge Base header out-of-scope links — focus-order consistency', () => {
  test('tab order is Learning Insights -> Trust Settings -> Import Runbook -> search box, matching visual left-to-right order', async ({
    page,
  }) => {
    await page.route('**/api/v1/knowledge/**', async (route) => {
      const url = new URL(route.request().url())
      if (!url.pathname.endsWith('/api/v1/knowledge/') && !url.pathname.endsWith('/api/v1/knowledge')) {
        return route.fallback()
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ query: '', entries: [], has_exact_matches: true, error: null }),
      })
    })
    await page.goto('/app/knowledge')

    const learningLink = page.getByRole('link', { name: 'Learning Insights' })
    await learningLink.focus()
    await expect(learningLink).toBeFocused()

    await page.keyboard.press('Tab')
    await expect(page.getByRole('link', { name: 'Trust Settings' })).toBeFocused()

    await page.keyboard.press('Tab')
    await expect(page.getByRole('link', { name: 'Import Runbook' })).toBeFocused()

    await page.keyboard.press('Tab')
    await expect(page.getByLabel('Search knowledge base')).toBeFocused()
  })
})
