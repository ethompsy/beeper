import type { Preview } from '@storybook/react-vite'
import '../src/theme/tokens.css'

/**
 * Global Storybook preview config (Task 1.4).
 *
 * Imports the Task 1.2 dark-first tokens.css as the single stylesheet for
 * every story — stories consume the same token classes production views
 * will use; nothing is redeclared here.
 */
const preview: Preview = {
  parameters: {
    backgrounds: {
      default: 'beeper-dark',
      values: [{ name: 'beeper-dark', value: '#0f0f1a' }],
    },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
  },
}

export default preview
