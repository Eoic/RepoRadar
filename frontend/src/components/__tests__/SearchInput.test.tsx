import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { SearchInput } from '../SearchInput'

describe('SearchInput', () => {
  it('renders input and button', () => {
    render(<SearchInput onSearch={() => {}} isLoading={false} />)
    expect(screen.getByRole('textbox')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /search/i })).toBeInTheDocument()
  })

  it('calls onSearch with trimmed value on submit', async () => {
    const user = userEvent.setup()
    const onSearch = vi.fn()
    render(<SearchInput onSearch={onSearch} isLoading={false} />)

    await user.type(screen.getByRole('textbox'), '  facebook/react  ')
    await user.click(screen.getByRole('button', { name: /search/i }))

    expect(onSearch).toHaveBeenCalledWith('facebook/react')
  })

  it('does not submit with empty input', async () => {
    const user = userEvent.setup()
    const onSearch = vi.fn()
    render(<SearchInput onSearch={onSearch} isLoading={false} />)

    // Button should be disabled with empty input
    expect(screen.getByRole('button', { name: /search/i })).toBeDisabled()

    // Type spaces only
    await user.type(screen.getByRole('textbox'), '   ')
    expect(screen.getByRole('button')).toBeDisabled()
    expect(onSearch).not.toHaveBeenCalled()
  })

  it('disables input and button when loading', () => {
    render(<SearchInput onSearch={() => {}} isLoading={true} />)
    expect(screen.getByRole('textbox')).toBeDisabled()
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('shows loading text when searching', () => {
    render(<SearchInput onSearch={() => {}} isLoading={true} />)
    expect(screen.getByRole('button')).toHaveTextContent('Searching...')
  })

  it('handles Enter key submission', async () => {
    const user = userEvent.setup()
    const onSearch = vi.fn()
    render(<SearchInput onSearch={onSearch} isLoading={false} />)

    const input = screen.getByRole('textbox')
    await user.type(input, 'facebook/react{Enter}')
    expect(onSearch).toHaveBeenCalledWith('facebook/react')
  })

  it('has role="search" and proper ARIA attributes', () => {
    render(<SearchInput onSearch={() => {}} isLoading={false} />)
    expect(screen.getByRole('search')).toBeInTheDocument()
    expect(screen.getByLabelText('Repository URL')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toHaveAttribute('aria-describedby', 'search-hint')
  })
})
