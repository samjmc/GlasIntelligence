// Vite statically replaces import.meta.env.* at build time, so a production build
// with VITE_DEMO_MODE unset can dead-code-eliminate every demo branch.
// Note: vite.config.js sets envDir: '..', so these are read from the repo root.

export const isDemoMode = import.meta.env.VITE_DEMO_MODE === '1'

// Derived from the measured run length in Task 3: run_length_ms / 90000.
// 1 until a real tape exists.
// A non-finite or ≤0 value fails loudly rather than silently falling back to 1:
// production sets this to duration_ms / 90000, so a bad paste (e.g. "1x" or "0")
// would ship a demo that runs at 1× speed (minutes instead of ~90 s) with no error.
const _rawSpeedup = Number(import.meta.env.VITE_DEMO_SPEEDUP)
if (import.meta.env.VITE_DEMO_MODE === '1' && import.meta.env.VITE_DEMO_SPEEDUP !== undefined) {
  if (!Number.isFinite(_rawSpeedup) || _rawSpeedup <= 0) {
    throw new Error(
      `[demo] VITE_DEMO_SPEEDUP must be a finite positive number; got: ${import.meta.env.VITE_DEMO_SPEEDUP}`,
    )
  }
}
export const DEMO_SPEEDUP = _rawSpeedup > 0 && Number.isFinite(_rawSpeedup) ? _rawSpeedup : 1

// The localStorage key under which Home.vue persists the active session id.
// Centralised here so adapter.js and Home.vue can't silently diverge on a rename.
export const SESSION_KEY = 'glas_active_session'
