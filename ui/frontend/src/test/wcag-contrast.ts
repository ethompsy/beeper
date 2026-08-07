/**
 * wcag-contrast.ts (Task 6.0)
 *
 * Small, dependency-free WCAG 2.x contrast-ratio calculator, used by
 * `contrast.test.ts` to PROVE (not assert-by-hardcoded-number) that the
 * design tokens in `theme/tokens.css` meet their required contrast ratio
 * against the surfaces they're actually paired with — including the
 * alpha-blended "translucent badge tint" case, since several components
 * pair a token with itself at reduced opacity over a surface (e.g.
 * `bg-status-critical/10`) rather than the solid token value.
 *
 * Formula: WCAG 2.x relative luminance + contrast ratio
 * (https://www.w3.org/TR/WCAG21/#dfn-relative-luminance /
 * https://www.w3.org/TR/WCAG21/#dfn-contrast-ratio). Test-only helper — not
 * part of the public component library (`src/lib/index.ts`), so it is not
 * exported there.
 */

export type Hex = `#${string}`

interface Rgb {
  r: number
  g: number
  b: number
}

/** Parses a `#rrggbb` (or `#rgb`) hex string into 0-255 channel values. */
export function hexToRgb(hex: string): Rgb {
  let h = hex.trim().replace(/^#/, '')
  if (h.length === 3) {
    h = h
      .split('')
      .map((c) => c + c)
      .join('')
  }
  if (!/^[0-9a-fA-F]{6}$/.test(h)) {
    throw new Error(`hexToRgb: not a valid 6-digit hex color: ${hex}`)
  }
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  }
}

/** sRGB channel (0-255) -> linear-light channel, per the WCAG relative-luminance definition. */
function linearize(channel255: number): number {
  const c = channel255 / 255
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
}

/** WCAG relative luminance (0 = black, 1 = white) of an sRGB color. */
export function relativeLuminance(hex: string): number {
  const { r, g, b } = hexToRgb(hex)
  return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)
}

/**
 * WCAG contrast ratio between two sRGB colors, in the range [1, 21].
 * Order-independent: (L_lighter + 0.05) / (L_darker + 0.05).
 */
export function contrastRatio(hexA: string, hexB: string): number {
  const lA = relativeLuminance(hexA)
  const lB = relativeLuminance(hexB)
  const lighter = Math.max(lA, lB)
  const darker = Math.min(lA, lB)
  return (lighter + 0.05) / (darker + 0.05)
}

/**
 * Simulates CSS `color-mix`/alpha compositing: a foreground color rendered
 * at `alpha` (0-1) opacity over an opaque background color, per the
 * standard "over" alpha-compositing formula (opaque backdrop, so the
 * result is always opaque too). Used to model Tailwind's `bg-{token}/NN`
 * opacity-modifier classes, which is how several badges apply these tokens
 * (e.g. `bg-status-critical/10`) rather than as a solid fill.
 */
export function alphaBlend(fgHex: string, alpha: number, bgHex: string): Hex {
  const fg = hexToRgb(fgHex)
  const bg = hexToRgb(bgHex)
  const mix = (f: number, b: number) => Math.round(f * alpha + b * (1 - alpha))
  const toHex2 = (n: number) => n.toString(16).padStart(2, '0')
  return `#${toHex2(mix(fg.r, bg.r))}${toHex2(mix(fg.g, bg.g))}${toHex2(mix(fg.b, bg.b))}` as Hex
}

/** WCAG 2.1 SC 1.4.3 / 1.4.11 thresholds. */
export const WCAG_AA_SMALL_TEXT = 4.5
export const WCAG_AA_LARGE_TEXT_OR_NON_TEXT = 3.0
