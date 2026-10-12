/**
 * Parse a server timestamp. The backend writes naive UTC times
 * ("2026-10-10T16:03:00"), which the browser would read as local time,
 * so a date-time with no zone is read as UTC.
 * @param {string | null | undefined} str
 * @returns {Date | null}
 */
export function parseServerDate(str) {
  if (!str) return null
  let s = String(str).trim().replace(' ', 'T')
  if (/T\d{2}:\d{2}/.test(s) && !/(Z|[+-]\d{2}:?\d{2})$/i.test(s)) s += 'Z'
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}

const pad2 = (n) => String(n).padStart(2, '0')

/**
 * Local date as YYYY-MM-DD.
 * @param {string | null | undefined} str
 * @returns {string}
 */
export function formatLocalDate(str) {
  const d = parseServerDate(str)
  if (!d) return ''
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

/**
 * Local time as HH:MM (24-hour).
 * @param {string | null | undefined} str
 * @returns {string}
 */
export function formatLocalTime(str) {
  const d = parseServerDate(str)
  if (!d) return ''
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

/**
 * Human-readable relative time from an ISO-8601 timestamp.
 * @param {string | null | undefined} iso
 * @returns {string}
 */
export function formatRelative(iso) {
  if (!iso) return '--'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '--'
  const diff = Date.now() - then
  const s = Math.floor(diff / 1000)
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} minute${m === 1 ? '' : 's'} ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} hour${h === 1 ? '' : 's'} ago`
  const d = Math.floor(h / 24)
  if (d < 7) return `${d} day${d === 1 ? '' : 's'} ago`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

/**
 * Absolute local date/time for tooltips.
 * @param {string | null | undefined} iso
 * @returns {string}
 */
export function formatAbsolute(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
