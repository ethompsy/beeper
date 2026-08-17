import type { Meta, StoryObj } from '@storybook/react-vite'
import { KbEntryNotFound } from './KbEntryNotFound'

const meta = {
  title: 'Library/KbEntryNotFound',
  component: KbEntryNotFound,
  tags: ['autodocs'],
} satisfies Meta<typeof KbEntryNotFound>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    entryId: 'kb-0042',
  },
}
