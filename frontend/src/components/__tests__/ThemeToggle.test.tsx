import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { ThemeToggle } from '../ThemeToggle'

describe('ThemeToggle', () => {
  it('renders light_mode icon when dark theme (switch to light)', () => {
    render(<ThemeToggle theme="dark" onToggle={() => {}} />)
    expect(screen.getByText('light_mode')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /switch to light theme/i })).toBeInTheDocument()
  })

  it('renders dark_mode icon when light theme (switch to dark)', () => {
    render(<ThemeToggle theme="light" onToggle={() => {}} />)
    expect(screen.getByText('dark_mode')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /switch to dark theme/i })).toBeInTheDocument()
  })

  it('calls onToggle when clicked', async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()
    render(<ThemeToggle theme="light" onToggle={onToggle} />)

    await user.click(screen.getByRole('button'))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('has correct aria-label per theme', () => {
    const { rerender } = render(<ThemeToggle theme="light" onToggle={() => {}} />)
    expect(screen.getByRole('button')).toHaveAttribute('aria-label', 'Switch to dark theme')

    rerender(<ThemeToggle theme="dark" onToggle={() => {}} />)
    expect(screen.getByRole('button')).toHaveAttribute('aria-label', 'Switch to light theme')
  })

  it('is keyboard accessible with Enter key', async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()
    render(<ThemeToggle theme="light" onToggle={onToggle} />)

    const button = screen.getByRole('button')
    button.focus()
    await user.keyboard('{Enter}')
    expect(onToggle).toHaveBeenCalledTimes(1)
  })
})
