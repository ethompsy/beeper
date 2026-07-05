/**
 * NotFoundMessage.test.tsx (Task 2.5) — invalid investigation id renders
 * "Investigation not found" content, meant to be mounted INSIDE the app
 * shell (sidebar visible) by the route — this test only proves the
 * message's own content; `InvestigationDetailPage.test.tsx` proves it's
 * reached for a 404 id, and `e2e/app-shell.spec.ts`-style specs prove
 * shell visibility for the detail route generally.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { NotFoundMessage } from '../components/NotFoundMessage'

describe('NotFoundMessage', () => {
  it('renders "Investigation not found" with the id in the body text', () => {
    render(<NotFoundMessage investigationId="INV-9999" />)
    expect(screen.getByRole('heading', { name: 'Investigation not found' })).toBeVisible()
    expect(screen.getByText(/INV-9999/)).toBeVisible()
  })
})
