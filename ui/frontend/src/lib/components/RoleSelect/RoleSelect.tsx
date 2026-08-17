import { cn } from '../../utils/cn'

/**
 * RoleSelect — controlled `admin`/`user` role picker (Task 8.7, ADR 0002
 * §6, FR60).
 *
 * A plain native `<select>` per the task instructions ("simplest and
 * accessible by default — do not add `@radix-ui/react-select` unless you
 * have a strong reason"): a two-option role picker has no need for
 * Radix Select's richer affordances (multi-level groups, custom item
 * rendering, virtualization), and a native `<select>` gets full keyboard
 * support, screen-reader announcement, and mobile-native picker UI for
 * free. Styled with the same token classes as `LoginForm`'s `<input>`
 * (border-surface-overlay / bg-surface-raised / focus-visible ring) so it
 * reads as part of the same form-control family.
 *
 * Presentational + controlled, matching `StatusGroupFilter`'s split: the
 * caller (`UserTable` row, or `UserFormDialog`) owns the actual PATCH/state
 * update; this component only renders the control and calls `onChange`.
 */
export type RoleSelectValue = 'admin' | 'user'

export interface RoleSelectProps {
  /** Associates the control with its label — must be unique per instance on the page (e.g. per table row). */
  id: string
  label: string
  value: RoleSelectValue
  onChange: (value: RoleSelectValue) => void
  /** True for SCIM-owned rows (read-only from this UI while in `oidc` mode) or while a mutation is in flight. */
  disabled?: boolean
  /** Visually hides `label` while keeping it in the accessibility tree (e.g. a table column already names the field). */
  hideLabel?: boolean
  className?: string
}

export function RoleSelect({
  id,
  label,
  value,
  onChange,
  disabled = false,
  hideLabel = false,
  className,
}: RoleSelectProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className={cn('text-sm font-medium text-text-secondary', hideLabel && 'sr-only')}>
        {label}
      </label>
      <select
        id={id}
        name={id}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value as RoleSelectValue)}
        className={cn(
          'w-full rounded-lg border border-surface-overlay bg-surface-raised px-3 py-2 text-sm text-text-primary',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
          'disabled:cursor-not-allowed disabled:opacity-60',
          className,
        )}
      >
        <option value="admin">Admin</option>
        <option value="user">User</option>
      </select>
    </div>
  )
}
