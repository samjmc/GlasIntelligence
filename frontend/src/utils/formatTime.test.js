import { describe, it, expect } from 'vitest'
import { parseServerDate, formatLocalDate, formatLocalTime } from './formatTime'

// The backend writes naive UTC timestamps. Read as local time they showed a run
// started at 17:03 Irish time as 16:03.

const pad2 = (n) => String(n).padStart(2, '0')

describe('server timestamps', () => {
  it('reads a timestamp with no zone as UTC', () => {
    expect(parseServerDate('2026-10-10T16:03:00').toISOString()).toBe('2026-10-10T16:03:00.000Z')
    expect(parseServerDate('2026-10-10 16:03:00.123456').toISOString()).toBe('2026-10-10T16:03:00.123Z')
  })

  it('keeps an explicit zone as given', () => {
    expect(parseServerDate('2026-10-10T16:03:00Z').toISOString()).toBe('2026-10-10T16:03:00.000Z')
    expect(parseServerDate('2026-10-10T16:03:00+01:00').toISOString()).toBe('2026-10-10T15:03:00.000Z')
  })

  it('formats in the browser local time zone', () => {
    const utc = new Date(Date.UTC(2026, 9, 10, 16, 3))
    expect(formatLocalTime('2026-10-10T16:03:00')).toBe(`${pad2(utc.getHours())}:${pad2(utc.getMinutes())}`)
    expect(formatLocalDate('2026-10-10T16:03:00')).toBe(
      `${utc.getFullYear()}-${pad2(utc.getMonth() + 1)}-${pad2(utc.getDate())}`,
    )
  })

  it('returns empty text for missing or bad input', () => {
    expect(parseServerDate('')).toBeNull()
    expect(formatLocalTime(null)).toBe('')
    expect(formatLocalDate('not a date')).toBe('')
  })
})
