/**
 * cn — classname merge utility (the standard shadcn-style helper).
 *
 * Combines `clsx` (conditional class composition) with `tailwind-merge`
 * (resolves conflicting Tailwind utility classes, last-wins) so consumers can
 * override library styling from the outside without specificity fights:
 *
 *   <StatusBadge className="text-lg" />  // overrides the badge's default text size
 *
 * This is the one small utility every shadcn-style component in this library
 * is built on — it is exported from the library's public API so external
 * consumers building on top of these primitives get the same tool.
 */
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}
