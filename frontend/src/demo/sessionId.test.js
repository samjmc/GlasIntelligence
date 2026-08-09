import { describe, it, expect } from 'vitest'
import { encodeDemoId, decodeDemoId } from './sessionId'

describe('demo session IDs', () => {
  it('round-trips a start time and scenario', () => {
    const id = encodeDemoId(1754650000000, 'energy-price-cap')
    const decoded = decodeDemoId(id)
    expect(decoded).toEqual({ startMs: 1754650000000, scenario: 'energy-price-cap' })
  })

  it('produces a URL-safe id with the demo_ prefix', () => {
    const id = encodeDemoId(1754650000000, 'energy-price-cap')
    expect(id.startsWith('demo_')).toBe(true)
    expect(id).toMatch(/^[A-Za-z0-9_-]+$/)
  })

  it('produces a different id each call for the same inputs', () => {
    const a = encodeDemoId(1754650000000, 'energy-price-cap')
    const b = encodeDemoId(1754650000000, 'energy-price-cap')
    expect(a).not.toBe(b)
  })

  it('returns null for a non-demo id', () => {
    expect(decodeDemoId('550e8400-e29b-41d4-a716-446655440000')).toBeNull()
    expect(decodeDemoId('')).toBeNull()
    expect(decodeDemoId('demo_notbase64')).toBeNull()
  })

  it('returns null when the scenario segment is missing', () => {
    expect(decodeDemoId('demo_MTc1NDY1MDAwMDAwMA')).toBeNull()
  })
})
