import { test, expect, type Page } from '@playwright/test'

/**
 * knowledge-base.spec.ts (Task 5.1)
 *
 * Real-browser coverage for the KB browse/search + entry-detail views,
 * complementing the Vitest/RTL coverage in
 * `src/routes/test/KnowledgeBasePage.test.tsx` /
 * `src/routes/test/KnowledgeEntryPage.test.tsx` with the parts that
 * genuinely need a real browser:
 *   - a real network layer (`page.route` intercepting the JSON API) rather
 *     than a `global.fetch` stub;
 *   - a genuine COLD load of a `?q=` permalink URL — a fresh `page.goto`
 *     straight to the URL, no prior in-app typing establishing state
 *     (FR53/FR29, matching `investigation-list.spec.ts`'s equivalent test);
 *   - real client-side navigation from the browse list into an entry
 *     (clicking a row is a router `Link`, not a full page reload).
 *
 * Runs against the *built* app (`vite preview`, matching the existing e2e
 * convention) — no Flask backend, so every test mocks
 * `**\/api/v1/knowledge/**` via `page.route`.
 */

interface MockEntrySummary {
  id: string
  entry_id: string
  entry_type: string
  title: string
  service: string | null
  created_at: string | null
  updated_at: string | null
  author: string | null
  version: number
  tags: string[]
  validation_status: string | null
  auto_published: boolean
  relevance_score: number | null
  snippet: string
}

function makeEntrySummary(overrides: Partial<MockEntrySummary>): MockEntrySummary {
  return {
    id: 'point-1',
    entry_id: 'kb-default',
    entry_type: 'investigation',
    title: 'checkout-service latency after deploy',
    service: 'checkout-service',
    created_at: '2026-06-01T10:00:00+00:00',
    updated_at: '2026-06-01T10:00:00+00:00',
    author: 'beeper',
    version: 1,
    tags: ['deploy'],
    validation_status: 'human-confirmed',
    auto_published: false,
    relevance_score: null,
    snippet: 'Connection pool exhaustion after a deploy.',
    ...overrides,
  }
}

async function mockKnowledgeListApi(
  page: Page,
  entriesByQuery: Record<string, MockEntrySummary[]>,
): Promise<void> {
  await page.route('**/api/v1/knowledge/**', async (route) => {
    const url = new URL(route.request().url())
    // Only intercept the browse/search list endpoint, not entry-detail
    // (`/api/v1/knowledge/<id>`) — this route matcher only has one path
    // segment beyond `/knowledge/`.
    if (!url.pathname.endsWith('/api/v1/knowledge/') && !url.pathname.endsWith('/api/v1/knowledge')) {
      return route.fallback()
    }
    const q = url.searchParams.get('q') ?? ''
    const entries = entriesByQuery[q] ?? []
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ query: q, entries, has_exact_matches: true, error: null }),
    })
  })
}

async function mockKnowledgeEntryApi(page: Page, entryId: string, body: object): Promise<void> {
  await page.route(`**/api/v1/knowledge/${entryId}`, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
}

test.describe('KB browse — real browser (FR28/NFR19)', () => {
  test('renders entry cards with title/type/service/snippet', async ({ page }) => {
    await mockKnowledgeListApi(page, {
      '': [
        makeEntrySummary({
          entry_id: 'kb-001',
          title: 'checkout-service latency after deploy',
          entry_type: 'investigation',
          service: 'checkout-service',
        }),
      ],
    })

    await page.goto('/app/knowledge')

    const card = page.getByRole('link', { name: /checkout-service latency after deploy/i })
    await expect(card).toBeVisible()
    await expect(card).toContainText('Investigation')
    await expect(card).toContainText('checkout-service')
    await expect(card).toContainText('Connection pool exhaustion after a deploy.')
  })

  test('empty knowledge base renders an explanatory empty state, never a blank frame', async ({ page }) => {
    await mockKnowledgeListApi(page, { '': [] })

    await page.goto('/app/knowledge')

    await expect(page.getByText('No knowledge base entries yet')).toBeVisible()
  })
})

test.describe('KB search permalink — cold load (Task 5.1, FR29/FR53)', () => {
  test('selecting a search updates the URL, and cold-loading that URL directly reproduces the filtered result', async ({
    page,
  }) => {
    await mockKnowledgeListApi(page, {
      '': [
        makeEntrySummary({ entry_id: 'kb-browse', title: 'Unrelated browse-only entry', service: 'other-service' }),
      ],
      latency: [
        makeEntrySummary({
          entry_id: 'kb-search-hit',
          title: 'checkout-service latency after deploy',
          service: 'checkout-service',
          relevance_score: 0.82,
        }),
      ],
    })

    // Part 1: typing in-app updates the address bar.
    await page.goto('/app/knowledge')
    await expect(page.getByRole('link', { name: /Unrelated browse-only entry/i })).toBeVisible()

    await page.getByLabel('Search knowledge base').fill('latency')
    await expect(page).toHaveURL(/[?&]q=latency(&|$)/, { timeout: 5000 })
    await expect(page.getByRole('link', { name: /checkout-service latency after deploy/i })).toBeVisible()

    // Part 2: a fresh, cold navigation straight to that URL — no prior
    // in-app typing, no prior page in this browsing context — reproduces
    // the identical search result. This is what happens when a teammate
    // pastes the copied link into a new tab.
    await page.goto('/app/knowledge?q=latency')
    await expect(page.getByRole('link', { name: /checkout-service latency after deploy/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /Unrelated browse-only entry/i })).toHaveCount(0)
    await expect(page.getByLabel('Search knowledge base')).toHaveValue('latency')
  })

  test('cold-loading a search permalink with zero matches renders "No results found", never a blank frame', async ({
    page,
  }) => {
    await mockKnowledgeListApi(page, { 'nonexistent-thing': [] })

    await page.goto('/app/knowledge?q=nonexistent-thing')

    await expect(page.getByText('No results found')).toBeVisible()
  })
})

test.describe('KB entry detail — real browser (FR31)', () => {
  test('clicking a browse-list card navigates client-side into the entry-detail view', async ({ page }) => {
    await mockKnowledgeListApi(page, {
      '': [makeEntrySummary({ entry_id: 'kb-001', title: 'checkout-service latency after deploy' })],
    })
    await mockKnowledgeEntryApi(page, 'kb-001', {
      entry: {
        id: 'point-1',
        entry_id: 'kb-001',
        entry_type: 'investigation',
        title: 'checkout-service latency after deploy',
        service: 'checkout-service',
        created_at: '2026-06-01T10:00:00+00:00',
        updated_at: '2026-06-01T10:00:00+00:00',
        author: 'beeper',
        version: 1,
        tags: ['deploy'],
        validation_status: 'human-confirmed',
        auto_published: false,
        relevance_score: null,
        content_html: '<p>Connection pool exhaustion after a deploy.</p>',
        root_cause: 'Connection pool exhaustion',
        resolution: 'Increased pool size',
        affected_services: ['checkout-service'],
      },
      related_entries: [],
      source_investigation: null,
      contributing_investigations: [],
    })

    await page.goto('/app/knowledge')
    await page.getByRole('link', { name: /checkout-service latency after deploy/i }).click()

    await expect(page).toHaveURL(/\/app\/knowledge\/kb-001$/)
    await expect(page.getByRole('heading', { name: 'checkout-service latency after deploy' })).toBeVisible()
    await expect(page.getByText('Incident Details')).toBeVisible()
    await expect(page.getByText('Connection pool exhaustion', { exact: true })).toBeVisible()
  })

  test('cold-loading an entry-detail permalink directly reproduces the identical view', async ({ page }) => {
    await mockKnowledgeEntryApi(page, 'kb-002', {
      entry: {
        id: 'point-2',
        entry_id: 'kb-002',
        entry_type: 'runbook',
        title: 'Restarting the payments worker pool',
        service: 'payments-api',
        created_at: '2026-05-20T00:00:00+00:00',
        updated_at: '2026-05-20T00:00:00+00:00',
        author: 'sre-team',
        version: 3,
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
    })

    await page.goto('/app/knowledge/kb-002')

    await expect(page.getByRole('heading', { name: 'Restarting the payments worker pool' })).toBeVisible()
    await expect(page.getByText('Runbook')).toBeVisible()
    await expect(page.getByText('Step-by-step recovery procedure.')).toBeVisible()
    // No Incident Details section when none of its fields are present.
    await expect(page.getByText('Incident Details')).toHaveCount(0)
  })

  test('an invalid entry id renders an in-shell "not found" message with the sidebar visible, not a bare 404', async ({
    page,
  }) => {
    await page.route('**/api/v1/knowledge/kb-missing', async (route) => {
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: 'not_found' }) })
    })

    await page.goto('/app/knowledge/kb-missing')

    await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
    await expect(page.getByText('Knowledge Base entry not found')).toBeVisible()
    await expect(page.getByText('Entry kb-missing not found.')).toBeVisible()
  })
})
