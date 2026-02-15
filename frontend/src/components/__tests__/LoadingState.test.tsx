import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { LoadingState } from '../LoadingState'

describe('LoadingState', () => {
  it('renders loading text and subtext', () => {
    render(<LoadingState />)
    expect(screen.getByText('Searching repositories...')).toBeInTheDocument()
    expect(screen.getByText(/Fetching metadata/)).toBeInTheDocument()
  })

  it('has role="status" and aria-live="polite"', () => {
    render(<LoadingState />)
    const container = screen.getByRole('status')
    expect(container).toHaveAttribute('aria-live', 'polite')
  })

  it('provides visually-hidden screen reader text', () => {
    const { container } = render(<LoadingState />)
    const hidden = container.querySelector('.visually-hidden')
    expect(hidden).toBeInTheDocument()
    expect(hidden).toHaveTextContent('Loading search results')
  })
})
