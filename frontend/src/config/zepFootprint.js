/**
 * Single source of truth for client-side Zep/API polling footprint.
 * Values come from Vite env at build time (see Dockerfile.prod, docker-compose.prod.yml, .env.example).
 */

function parseIntEnv(raw, fallback) {
  if (raw === undefined || raw === null || raw === '') return fallback
  const n = Number.parseInt(String(raw), 10)
  return Number.isFinite(n) && n >= 0 ? n : fallback
}

function parseBoolEnv(raw, fallback) {
  if (raw === undefined || raw === null || raw === '') return fallback
  const s = String(raw).toLowerCase()
  if (s === '1' || s === 'true' || s === 'yes') return true
  if (s === '0' || s === 'false' || s === 'no') return false
  return fallback
}

const env = import.meta.env

/** Polling when graph exists and not in active Zep build (ms) */
export const graphPollMsVisible = parseIntEnv(env.VITE_ZEP_GRAPH_POLL_VISIBLE_MS, 120_000)

/** Polling when document is hidden (ms) */
export const graphPollMsHidden = parseIntEnv(env.VITE_ZEP_GRAPH_POLL_HIDDEN_MS, 300_000)

/** Faster polling while Zep graph is building (ms) */
export const graphPollDuringBuildMs = parseIntEnv(env.VITE_ZEP_GRAPH_POLL_DURING_BUILD_MS, 8_000)

/**
 * Auto-poll graph during simulation (ms). 0 = disabled (manual refresh only).
 */
export const graphPollWhileSimulatingMs = parseIntEnv(env.VITE_ZEP_GRAPH_POLL_WHILE_SIMULATING_MS, 0)

/** Skip graph poll ticks when document.hidden */
export const graphSkipPollWhenDocumentHidden = parseBoolEnv(env.VITE_ZEP_GRAPH_SKIP_WHEN_HIDDEN, true)

/** Step 2 prepare/config polling initial interval (ms) */
export const step2PollMsInitial = parseIntEnv(env.VITE_ZEP_STEP2_POLL_MS_INITIAL, 2000)

/** Step 2 polling after stable ready (ms) */
export const step2PollMsDecay = parseIntEnv(env.VITE_ZEP_STEP2_POLL_MS_DECAY, 5000)

/** Step 3 run status interval (ms) */
export const step3StatusPollMs = parseIntEnv(env.VITE_ZEP_STEP3_STATUS_MS, 4000)

/** Step 3 action detail interval (ms) */
export const step3DetailPollMs = parseIntEnv(env.VITE_ZEP_STEP3_DETAIL_MS, 6000)

/**
 * Delay until the next graph poll attempt (ms).
 * @param {{ graphBuilding?: boolean, documentHidden?: boolean }} opts
 * @returns {number}
 */
export function getGraphPollIntervalMs(opts = {}) {
  const { graphBuilding = false, documentHidden = false } = opts
  if (documentHidden) return graphPollMsHidden
  if (graphBuilding) return graphPollDuringBuildMs
  return graphPollMsVisible
}
