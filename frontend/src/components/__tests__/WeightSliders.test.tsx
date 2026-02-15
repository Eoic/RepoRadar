import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { WeightSliders } from '../WeightSliders'

describe('WeightSliders', () => {
  it('displays correct weight percentages', () => {
    render(<WeightSliders purposeWeight={0.7} onWeightChange={() => {}} />)
    expect(screen.getByText('70%')).toBeInTheDocument()
    expect(screen.getByText('30%')).toBeInTheDocument()
  })

  it('calculates stack weight correctly (complementary)', () => {
    render(<WeightSliders purposeWeight={0.6} onWeightChange={() => {}} />)
    expect(screen.getByText('60%')).toBeInTheDocument()
    expect(screen.getByText('40%')).toBeInTheDocument()
  })

  it('has proper ARIA attributes on slider', () => {
    render(<WeightSliders purposeWeight={0.7} onWeightChange={() => {}} />)
    const slider = screen.getByRole('slider')
    expect(slider).toHaveAttribute('aria-valuemin', '0')
    expect(slider).toHaveAttribute('aria-valuemax', '100')
    expect(slider).toHaveAttribute('aria-valuenow', '70')
    expect(slider).toHaveAttribute('aria-valuetext', 'Purpose 70%, Stack 30%')
  })

  it('is keyboard accessible (slider is focusable and has correct role)', () => {
    render(<WeightSliders purposeWeight={0.7} onWeightChange={() => {}} />)
    const slider = screen.getByRole('slider')
    slider.focus()
    expect(document.activeElement).toBe(slider)
  })
})
