import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ResultsList } from '../ResultsList'
import type { SearchResultItem } from '../../types/api'

const mockResults: SearchResultItem[] = [
  {
    full_name: 'facebook/react',
    url: 'https://github.com/facebook/react',
    description: 'UI library',
    topics: ['react'],
    language_primary: 'JavaScript',
    stars: 220000,
    similarity_score: 0.92,
    purpose_score: 0.88,
    stack_score: 0.95,
  },
  {
    full_name: 'vuejs/vue',
    url: 'https://github.com/vuejs/vue',
    description: 'Progressive framework',
    topics: ['vue'],
    language_primary: 'TypeScript',
    stars: 207000,
    similarity_score: 0.85,
    purpose_score: 0.82,
    stack_score: 0.87,
  },
]

describe('ResultsList', () => {
  it('renders header with query repo name', () => {
    render(
      <ResultsList results={mockResults} indexedCount={1000} searchTimeMs={42.5} queryRepo="angular/angular" />
    )
    expect(screen.getByText('angular/angular')).toBeInTheDocument()
    expect(screen.getByText(/Showing results similar to/)).toBeInTheDocument()
  })

  it('displays search statistics', () => {
    render(
      <ResultsList results={mockResults} indexedCount={1000} searchTimeMs={42.5} queryRepo="test/repo" />
    )
    expect(screen.getByText(/2 matches/)).toBeInTheDocument()
    expect(screen.getByText(/43ms/)).toBeInTheDocument()
    expect(screen.getByText(/1,000 repos indexed/)).toBeInTheDocument()
  })

  it('renders all result cards', () => {
    render(
      <ResultsList results={mockResults} indexedCount={1000} searchTimeMs={42} queryRepo="test/repo" />
    )
    expect(screen.getByText('facebook/react')).toBeInTheDocument()
    expect(screen.getByText('vuejs/vue')).toBeInTheDocument()
  })

  it('shows no-results message when empty', () => {
    render(
      <ResultsList results={[]} indexedCount={1000} searchTimeMs={10} queryRepo="test/repo" />
    )
    expect(screen.getByText(/No similar repositories found/)).toBeInTheDocument()
  })

  it('uses semantic HTML (section, h2, ul, li)', () => {
    const { container } = render(
      <ResultsList results={mockResults} indexedCount={1000} searchTimeMs={42} queryRepo="test/repo" />
    )
    expect(container.querySelector('section')).toBeInTheDocument()
    expect(container.querySelector('h2')).toBeInTheDocument()
    expect(container.querySelector('ul')).toBeInTheDocument()
    expect(container.querySelectorAll('li')).toHaveLength(2)
  })

  it('uses singular "match" for single result', () => {
    render(
      <ResultsList results={[mockResults[0]]} indexedCount={1000} searchTimeMs={42} queryRepo="test/repo" />
    )
    expect(screen.getByText(/1 match ·/)).toBeInTheDocument()
  })
})
