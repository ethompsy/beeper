import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { LoginForm } from './LoginForm'

const meta = {
  title: 'Library/LoginForm',
  component: LoginForm,
  tags: ['autodocs'],
} satisfies Meta<typeof LoginForm>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: { onSubmit: () => {} },
}

export const Loading: Story = {
  args: { onSubmit: () => {}, loading: true },
}

export const WithError: Story = {
  args: {
    onSubmit: () => {},
    error: 'Invalid username or password.',
  },
}

/** Wires a fake ~600ms submit that always fails, to show the loading -> error cycle. */
export const Interactive: Story = {
  render: () => {
    function Wrapper() {
      const [loading, setLoading] = useState(false)
      const [error, setError] = useState<string | null>(null)

      function handleSubmit() {
        setLoading(true)
        setError(null)
        window.setTimeout(() => {
          setLoading(false)
          setError('Invalid username or password.')
        }, 600)
      }

      return <LoginForm onSubmit={handleSubmit} loading={loading} error={error} />
    }
    return <Wrapper />
  },
}
