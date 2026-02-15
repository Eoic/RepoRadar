import { describe, it, expect, vi, beforeEach } from 'vitest'
import { searchRepos, getHealth, indexRepo } from '../client'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

beforeEach(() => {
  mockFetch.mockReset()
})

describe('searchRepos', () => {
  it('sends correct POST request and parses response', async () => {
    const mockResponse = {
      query_repo: { full_name: 'test/repo' },
      results: [],
      indexed_count: 100,
      search_time_ms: 42,
    }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    })

    const result = await searchRepos({
      repo_url: 'https://github.com/test/repo',
      weight_purpose: 0.7,
      weight_stack: 0.3,
      limit: 20,
      min_stars: 0,
    })

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/search',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_url: 'https://github.com/test/repo',
          weight_purpose: 0.7,
          weight_stack: 0.3,
          limit: 20,
          min_stars: 0,
        }),
        signal: expect.any(AbortSignal),
      }),
    )
    expect(result).toEqual(mockResponse)
  })

  it('throws on failed request with detail message', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ detail: 'Repo not found' }),
    })

    await expect(
      searchRepos({ repo_url: 'bad', weight_purpose: 0.7, weight_stack: 0.3, limit: 20, min_stars: 0 }),
    ).rejects.toThrow('Repo not found')
  })

  it('throws on network error', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'))

    await expect(
      searchRepos({ repo_url: 'x', weight_purpose: 0.7, weight_stack: 0.3, limit: 20, min_stars: 0 }),
    ).rejects.toThrow('Network error')
  })
})

describe('getHealth', () => {
  it('fetches correct endpoint', async () => {
    const mockHealth = { status: 'ok', indexed_repos: 500, github_rate_limit_remaining: 4000 }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockHealth),
    })

    const result = await getHealth()
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/health',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
    expect(result).toEqual(mockHealth)
  })
})

describe('indexRepo', () => {
  it('sends correct POST request', async () => {
    const mockResult = { status: 'indexed', repo_id: 1, full_name: 'test/repo' }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockResult),
    })

    const result = await indexRepo('https://github.com/test/repo')
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/index',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_url: 'https://github.com/test/repo' }),
        signal: expect.any(AbortSignal),
      }),
    )
    expect(result).toEqual(mockResult)
  })

  it('throws on failure', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ detail: 'Rate limited' }),
    })

    await expect(indexRepo('https://github.com/test/repo')).rejects.toThrow('Rate limited')
  })
})
