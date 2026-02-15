import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ResultCard } from '../ResultCard'
import type { SearchResultItem } from '../../types/api'

const mockResult: SearchResultItem = {
  full_name: 'facebook/react',
  url: 'https://github.com/facebook/react',
  description: 'A declarative, efficient, and flexible JavaScript library for building user interfaces.',
  topics: ['javascript', 'react', 'ui', 'frontend', 'library'],
  language_primary: 'JavaScript',
  stars: 220000,
  similarity_score: 0.92,
  purpose_score: 0.88,
  stack_score: 0.95,
}

describe('ResultCard', () => {
  it('renders repo name, description, stars, language, and topics (max 4)', () => {
    render(<ResultCard result={mockResult} rank={0} />)
    expect(screen.getByText('facebook/react')).toBeInTheDocument()
    expect(screen.getByText(/A declarative, efficient/)).toBeInTheDocument()
    expect(screen.getByText(/220,000/)).toBeInTheDocument()
    expect(screen.getByText('JavaScript')).toBeInTheDocument()

    // Max 4 topics
    expect(screen.getByText('javascript')).toBeInTheDocument()
    expect(screen.getByText('react')).toBeInTheDocument()
    expect(screen.getByText('ui')).toBeInTheDocument()
    expect(screen.getByText('frontend')).toBeInTheDocument()
    expect(screen.queryByText('library')).not.toBeInTheDocument()
  })

  it('displays rank correctly', () => {
    render(<ResultCard result={mockResult} rank={0} />)
    expect(screen.getByText('#1')).toBeInTheDocument()
  })

  it('link has correct href, target, and rel', () => {
    render(<ResultCard result={mockResult} rank={0} />)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', 'https://github.com/facebook/react')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('score bars show correct percentages', () => {
    render(<ResultCard result={mockResult} rank={0} />)
    expect(screen.getByText('92%')).toBeInTheDocument()
    expect(screen.getByText('88%')).toBeInTheDocument()
    expect(screen.getByText('95%')).toBeInTheDocument()
  })

  it('has accessible aria-label on link', () => {
    render(<ResultCard result={mockResult} rank={0} />)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('aria-label', 'facebook/react, 220,000 stars, 92% similar')
  })

  it('handles null description', () => {
    const noDesc = { ...mockResult, description: null }
    const { container } = render(<ResultCard result={noDesc} rank={0} />)
    expect(container.querySelector('.result-description')).not.toBeInTheDocument()
  })

  it('handles null language', () => {
    const noLang = { ...mockResult, language_primary: null }
    const { container } = render(<ResultCard result={noLang} rank={0} />)
    expect(container.querySelector('.result-lang')).not.toBeInTheDocument()
  })

  it('score bars have progressbar role with ARIA attributes', () => {
    render(<ResultCard result={mockResult} rank={0} />)
    const progressbars = screen.getAllByRole('progressbar')
    expect(progressbars).toHaveLength(3)

    const [overall, purpose, stack] = progressbars
    expect(overall).toHaveAttribute('aria-valuenow', '92')
    expect(overall).toHaveAttribute('aria-label', 'Overall score: 92%')
    expect(purpose).toHaveAttribute('aria-valuenow', '88')
    expect(purpose).toHaveAttribute('aria-label', 'Purpose score: 88%')
    expect(stack).toHaveAttribute('aria-valuenow', '95')
    expect(stack).toHaveAttribute('aria-label', 'Stack score: 95%')
  })
})
