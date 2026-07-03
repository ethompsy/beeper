import type { StorybookConfig } from '@storybook/react-vite'

/**
 * Storybook config (Task 1.4).
 *
 * Kept self-contained here per scope discipline — Storybook's Vite needs
 * (React + Tailwind plugins) are declared in `viteFinal` below rather than
 * touching the app's `vite.config.ts`, which Task 1.5 will extend with the
 * dev-proxy.
 */
const config: StorybookConfig = {
  stories: ['../src/lib/components/**/*.stories.@(ts|tsx)'],
  addons: ['@storybook/addon-docs'],
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
  async viteFinal(viteConfig) {
    const { default: tailwindcss } = await import('@tailwindcss/vite')
    return {
      ...viteConfig,
      plugins: [...(viteConfig.plugins ?? []), tailwindcss()],
    }
  },
}

export default config
