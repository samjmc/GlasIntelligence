// Vite statically replaces import.meta.env.* at build time, so a production build
// with VITE_DEMO_MODE unset can dead-code-eliminate every demo branch.
// Note: vite.config.js sets envDir: '..', so these are read from the repo root.

export const isDemoMode = import.meta.env.VITE_DEMO_MODE === '1'

// Derived from the measured run length in Task 3: run_length_ms / 90000.
// 1 until a real tape exists.
export const DEMO_SPEEDUP = Number(import.meta.env.VITE_DEMO_SPEEDUP) || 1

export const DEMO_TARGET_MS = 90000

// The localStorage key under which Home.vue persists the active session id.
// Centralised here so adapter.js and Home.vue can't silently diverge on a rename.
export const SESSION_KEY = 'glas_active_session'
