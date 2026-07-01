/**
 * LINT FIXTURE — deliberately violating component.
 *
 * This file is NOT compiled into the production bundle.
 * It exists solely to assert that eslint-plugin-tailwindcss catches:
 *   (a) hardcoded color via arbitrary syntax: bg-[#0f0f1a], text-[#f8fafc]
 *   (b) hardcoded spacing via arbitrary syntax: p-[13px]
 *   (c) hardcoded motion/duration via arbitrary syntax: duration-[200ms]
 *
 * The lint-enforcement test asserts ESLint exits non-zero on this file
 * and that the output mentions the `no-arbitrary-value` rule.
 */

export function ViolatingComponent() {
  return (
    // (a) hardcoded colors — should be bg-surface-base, text-text-primary
    // (b) hardcoded spacing — should be p-3
    // (c) hardcoded duration — should use transition-all (token-based)
    <div
      className="bg-[#0f0f1a] p-[13px] duration-[200ms] text-[#f8fafc]"
    >
      Violating element
    </div>
  )
}
