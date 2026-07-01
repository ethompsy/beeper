/**
 * LINT FIXTURE — clean component (design-system compliant).
 *
 * This file is NOT compiled into the production bundle.
 * It exists solely to assert that ESLint exits 0 on a component that:
 *   (a) uses only token classes (no arbitrary values)
 *   (b) carries motion-reduce:transition-none on every animated element
 *
 * The lint-enforcement test asserts ESLint exits 0 on this file.
 */

export function CleanComponent() {
  return (
    <div
      className="bg-surface-base p-3 transition-all ease-in-out motion-reduce:transition-none text-text-primary"
    >
      <span className="text-status-healthy">Active</span>
      <span className="text-primary">Link</span>
    </div>
  )
}
