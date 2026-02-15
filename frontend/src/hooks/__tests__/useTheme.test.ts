import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useTheme } from '../useTheme'

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    vi.mocked(window.matchMedia).mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  })

  it('defaults to light when no saved preference and system is light', () => {
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('light')
  })

  it('defaults to dark when system prefers dark', () => {
    vi.mocked(window.matchMedia).mockImplementation((query: string) => ({
      matches: query === '(prefers-color-scheme: dark)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')
  })

  it('uses saved theme from localStorage', () => {
    localStorage.setItem('reporadar-theme', 'dark')
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')
  })

  it('toggles theme and persists to localStorage', () => {
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('light')

    act(() => { result.current.toggleTheme() })
    expect(result.current.theme).toBe('dark')
    expect(localStorage.setItem).toHaveBeenCalledWith('reporadar-theme', 'dark')

    act(() => { result.current.toggleTheme() })
    expect(result.current.theme).toBe('light')
    expect(localStorage.setItem).toHaveBeenCalledWith('reporadar-theme', 'light')
  })

  it('updates data-theme attribute on HTML element', () => {
    const { result } = renderHook(() => useTheme())
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')

    act(() => { result.current.toggleTheme() })
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })
})
