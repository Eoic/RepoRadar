import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import App from '../App'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

beforeEach(() => {
  mockFetch.mockReset()
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')

  // Default health response
  mockFetch.mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ status: 'ok', indexed_repos: 500, github_rate_limit_remaining: 4000 }),
  })
})

describe('App', () => {
  it('renders header and search input', () => {
    render(<App />)
    expect(screen.getByText('Radar')).toBeInTheDocument()
    expect(screen.getByRole('search')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('loads health data on mount', async () => {
    render(<App />)
    await waitFor(() => {
      expect(screen.getByText('500')).toBeInTheDocument()
    })
  })

  it('performs search and displays results', async () => {
    const user = userEvent.setup()
    const searchResponse = {
      query_repo: { full_name: 'test/repo' },
      results: [
        {
          full_name: 'similar/repo',
          url: 'https://github.com/similar/repo',
          description: 'A similar repo',
          topics: ['test'],
          language_primary: 'TypeScript',
          stars: 1000,
          similarity_score: 0.85,
          purpose_score: 0.8,
          stack_score: 0.9,
        },
      ],
      indexed_count: 500,
      search_time_ms: 42,
    }

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'ok', indexed_repos: 500, github_rate_limit_remaining: 4000 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(searchResponse),
      })

    render(<App />)

    await user.type(screen.getByRole('textbox'), 'test/repo')
    await user.click(screen.getByRole('button', { name: /search/i }))

    await waitFor(() => {
      expect(screen.getByText('similar/repo')).toBeInTheDocument()
    })
  })

  it('displays error on search failure', async () => {
    const user = userEvent.setup()

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'ok', indexed_repos: 500, github_rate_limit_remaining: 4000 }),
      })
      .mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({ detail: 'Repository not found' }),
      })

    render(<App />)

    await user.type(screen.getByRole('textbox'), 'bad/repo')
    await user.click(screen.getByRole('button', { name: /search/i }))

    await waitFor(() => {
      expect(screen.getByText('Repository not found')).toBeInTheDocument()
    })
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('theme toggle changes theme', async () => {
    const user = userEvent.setup()
    render(<App />)

    // Default is light
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')

    await user.click(screen.getByRole('button', { name: /switch to dark theme/i }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')

    await user.click(screen.getByRole('button', { name: /switch to light theme/i }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('skip-to-content link is keyboard accessible', () => {
    render(<App />)
    const skipLink = screen.getByText('Skip to main content')
    expect(skipLink).toBeInTheDocument()
    expect(skipLink).toHaveAttribute('href', '#main-content')
    expect(document.getElementById('main-content')).toBeInTheDocument()
  })
})
