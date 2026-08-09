/**
 * RoleSelect.test.tsx (Task 8.7 — ADR 0002 §6, FR60).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RoleSelect } from '../components/RoleSelect'

describe('RoleSelect', () => {
  it('renders a labeled select with admin/user options and the current value selected', () => {
    render(<RoleSelect id="role-1" label="Role" value="admin" onChange={() => {}} />)
    const select = screen.getByLabelText('Role') as HTMLSelectElement
    expect(select.value).toBe('admin')
    expect(screen.getByRole('option', { name: 'Admin' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'User' })).toBeInTheDocument()
  })

  it('calls onChange with the new value when the user selects a different option', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<RoleSelect id="role-1" label="Role" value="user" onChange={onChange} />)

    await user.selectOptions(screen.getByLabelText('Role'), 'admin')

    expect(onChange).toHaveBeenCalledExactlyOnceWith('admin')
  })

  it('is disabled when disabled=true (e.g. a SCIM-owned read-only row)', () => {
    render(<RoleSelect id="role-1" label="Role" value="user" onChange={() => {}} disabled />)
    expect(screen.getByLabelText('Role')).toBeDisabled()
  })

  it('visually hides the label (sr-only) but keeps it in the accessibility tree when hideLabel is set', () => {
    render(<RoleSelect id="role-1" label="Role" value="user" onChange={() => {}} hideLabel />)
    const label = screen.getByText('Role')
    expect(label).toHaveClass('sr-only')
    expect(screen.getByLabelText('Role')).toBeInTheDocument()
  })
})
