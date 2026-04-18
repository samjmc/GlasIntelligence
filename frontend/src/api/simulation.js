import service, { requestWithRetry } from './index'

/**
 * Create simulation
 * @param {Object} data - { project_id, graph_id?, enable_twitter?, enable_reddit? }
 */
export const createSimulation = (data) => {
  return requestWithRetry(() => service.post('/api/simulation/create', data), 3, 1000)
}

/**
 * Prepare simulation environment (async task)
 * @param {Object} data - { simulation_id, entity_types?, use_llm_for_profiles?, parallel_profile_count?, force_regenerate? }
 */
export const prepareSimulation = (data) => {
  return requestWithRetry(() => service.post('/api/simulation/prepare', data), 3, 1000)
}

/**
 * Query preparation task progress
 * @param {Object} data - { task_id?, simulation_id? }
 */
export const getPrepareStatus = (data) => {
  return service.post('/api/simulation/prepare/status', data)
}

/**
 * Get simulation status
 * @param {string} simulationId
 */
export const getSimulation = (simulationId) => {
  return service.get(`/api/simulation/${simulationId}`)
}

/**
 * Get simulation Agent Profiles
 * @param {string} simulationId
 * @param {string} platform - 'reddit' | 'twitter'
 */
export const getSimulationProfiles = (simulationId, platform = 'reddit') => {
  return service.get(`/api/simulation/${simulationId}/profiles`, { params: { platform } })
}

/**
 * Get Agent Profiles in real-time as they are generated
 * @param {string} simulationId
 * @param {string} platform - 'reddit' | 'twitter'
 */
export const getSimulationProfilesRealtime = (simulationId, platform = 'reddit') => {
  return service.get(`/api/simulation/${simulationId}/profiles/realtime`, { params: { platform } })
}

/**
 * Get simulation config
 * @param {string} simulationId
 */
export const getSimulationConfig = (simulationId) => {
  return service.get(`/api/simulation/${simulationId}/config`)
}

/**
 * Get simulation config in real-time as it is generated
 * @param {string} simulationId
 * @returns {Promise} Returns config info including metadata and config content
 */
export const getSimulationConfigRealtime = (simulationId) => {
  return service.get(`/api/simulation/${simulationId}/config/realtime`)
}

/**
 * List all simulations
 * @param {string} projectId - Optional, filter by project ID
 */
export const listSimulations = (projectId) => {
  const params = projectId ? { project_id: projectId } : {}
  return service.get('/api/simulation/list', { params })
}

/**
 * Start simulation
 * @param {Object} data - { simulation_id, platform?, max_rounds?, enable_graph_memory_update? }
 */
export const startSimulation = (data) => {
  return requestWithRetry(() => service.post('/api/simulation/start', data), 3, 1000)
}

/**
 * Stop simulation
 * @param {Object} data - { simulation_id }
 */
export const stopSimulation = (data) => {
  return service.post('/api/simulation/stop', data)
}

/**
 * Get simulation run status in real-time
 * @param {string} simulationId
 */
export const getRunStatus = (simulationId) => {
  return service.get(`/api/simulation/${simulationId}/run-status`)
}

/**
 * Get simulation run status detail (includes recent actions)
 * @param {string} simulationId
 */
export const getRunStatusDetail = (simulationId) => {
  return service.get(`/api/simulation/${simulationId}/run-status/detail`)
}

/**
 * Get simulation posts
 * @param {string} simulationId
 * @param {string} platform - 'reddit' | 'twitter'
 * @param {number} limit - Number of items to return
 * @param {number} offset - Offset
 */
export const getSimulationPosts = (simulationId, platform = 'reddit', limit = 50, offset = 0) => {
  return service.get(`/api/simulation/${simulationId}/posts`, {
    params: { platform, limit, offset }
  })
}

/**
 * Get simulation timeline (aggregated by round)
 * @param {string} simulationId
 * @param {number} startRound - Start round
 * @param {number} endRound - End round
 */
export const getSimulationTimeline = (simulationId, startRound = 0, endRound = null) => {
  const params = { start_round: startRound }
  if (endRound !== null) {
    params.end_round = endRound
  }
  return service.get(`/api/simulation/${simulationId}/timeline`, { params })
}

/**
 * Get Agent stats
 * @param {string} simulationId
 */
export const getAgentStats = (simulationId) => {
  return service.get(`/api/simulation/${simulationId}/agent-stats`)
}

/**
 * Get simulation action history
 * @param {string} simulationId
 * @param {Object} params - { limit, offset, platform, agent_id, round_num }
 */
export const getSimulationActions = (simulationId, params = {}) => {
  return service.get(`/api/simulation/${simulationId}/actions`, { params })
}

/**
 * Close simulation environment (graceful shutdown)
 * @param {Object} data - { simulation_id, timeout? }
 */
export const closeSimulationEnv = (data) => {
  return service.post('/api/simulation/close-env', data)
}

/**
 * Get simulation environment status
 * @param {Object} data - { simulation_id }
 */
export const getEnvStatus = (data) => {
  return service.post('/api/simulation/env-status', data)
}

/**
 * Batch interview Agents
 * @param {Object} data - { simulation_id, interviews: [{ agent_id, prompt }] }
 */
export const interviewAgents = (data) => {
  return requestWithRetry(() => service.post('/api/simulation/interview/batch', data), 3, 1000)
}

/**
 * Get simulation history list (with project details)
 * Used for home page historical project display
 * @param {number} limit - Limit on number of items to return
 */
export const getSimulationHistory = (limit = 20) => {
  return service.get('/api/simulation/history', { params: { limit } })
}

/**
 * Start deep research (async background task)
 * @param {string} scenario - The scenario prompt to research
 * @param {Object} [angleOverrides] - Optional { angle_id: true|false } overrides
 */
export const startDeepResearch = (scenario, angleOverrides) => {
  const body = { prompt: scenario }
  if (angleOverrides && Object.keys(angleOverrides).length > 0) {
    body.angle_overrides = angleOverrides
  }
  return service.post('/api/source/deep-research', body)
}

/**
 * Get deep research task status
 * @param {string} taskId
 */
export const getDeepResearchStatus = (taskId) => {
  return service.get(`/api/source/deep-research/status/${taskId}`)
}

/**
 * Get completed deep research dossier
 * @param {string} taskId
 */
export const getDeepResearchResult = (taskId) => {
  return service.get(`/api/source/deep-research/result/${taskId}`)
}

/**
 * Get LLM-generated follow-up scenario suggestions
 * @param {Object} data - { simulation_id?, report_id? }
 */
export const suggestFollowups = (data) => {
  return service.post('/api/simulation/suggest-followups', data)
}

/**
 * Create a decision bundle with LLM-generated sub-scenarios
 * @param {Object} data - { title, decision_context }
 */
export const createBundle = (data) => {
  return service.post('/api/bundle/create', data)
}

/**
 * Get a decision bundle by ID
 * @param {string} bundleId
 */
export const getBundle = (bundleId) => {
  return service.get(`/api/bundle/${bundleId}`)
}

/**
 * List user's decision bundles
 */
export const listBundles = () => {
  return service.get('/api/bundle/list')
}

/**
 * Mark a bundle scenario as completed
 * @param {string} bundleId
 * @param {Object} data - { scenario_index, simulation_id, report_id }
 */
export const completeBundleScenario = (bundleId, data) => {
  return service.post(`/api/bundle/${bundleId}/complete-scenario`, data)
}

/**
 * Update a decision bundle (scenarios, status, etc.)
 * @param {string} bundleId
 * @param {Object} fields
 */
export const updateBundle = (bundleId, fields) => {
  return service.patch(`/api/bundle/${bundleId}`, fields)
}

/**
 * Start executing all scenarios in a bundle sequentially
 * @param {string} bundleId
 * @param {Object} data - { session_id }
 */
export const runBundle = (bundleId, data) => {
  return service.post(`/api/bundle/${bundleId}/run`, data)
}

/**
 * Get bundle execution status
 * @param {string} bundleId
 */
export const getBundleStatus = (bundleId) => {
  return service.get(`/api/bundle/${bundleId}/status`)
}

/**
 * Get bundle comparison data
 * @param {string} bundleId
 */
export const getBundleComparison = (bundleId) => {
  return service.get(`/api/bundle/${bundleId}/comparison`)
}

/**
 * Get bundle executive synthesis JSON (if generated)
 * @param {string} bundleId
 */
export const getBundleSynthesis = (bundleId) => {
  return service.get(`/api/bundle/${bundleId}/synthesis`)
}

/**
 * PATCH branch weights; server recomputes marginals
 * @param {string} bundleId
 * @param {{ branch_weights: Array<{ scenario_index: number, p_branch: number }> }} body
 */
export const patchBundleSynthesisWeights = (bundleId, body) => {
  return service.patch(`/api/bundle/${bundleId}/synthesis/weights`, body)
}

/**
 * Delete a decision bundle
 * @param {string} bundleId
 */
export const deleteBundle = (bundleId) => {
  return service.delete(`/api/bundle/${bundleId}`)
}

/**
 * Compare multiple report payloads side-by-side
 * @param {Object} data - { report_ids: [id1, id2, ...] }
 */
export const compareReports = (data) => {
  return service.post('/api/report/compare', data)
}

/**
 * Create a simulation reminder
 * @param {Object} data - { simulation_id, scenario, remind_at }
 */
export const createReminder = (data) => {
  return service.post('/api/simulation/reminder', data)
}

/**
 * List user's simulation reminders
 */
export const listReminders = () => {
  return service.get('/api/simulation/reminders')
}

// ── Scenario Sessions ──

/**
 * Create a scenario session (deducts 1 credit)
 * @param {string} prompt
 * @param {Object} [decisionContext]
 */
export const createSession = (prompt, decisionContext) => {
  return service.post('/api/session', { prompt, decision_context: decisionContext || {} })
}

/**
 * Get user's active (non-completed/abandoned) sessions
 */
export const getActiveSessions = () => {
  return service.get('/api/session/active')
}

/**
 * Get a session by ID
 * @param {string} sessionId
 */
export const getSession = (sessionId) => {
  return service.get(`/api/session/${sessionId}`)
}

/**
 * Update session fields (prompt, decision_context, bundle_config)
 * @param {string} sessionId
 * @param {Object} fields
 */
export const updateSession = (sessionId, fields) => {
  return service.patch(`/api/session/${sessionId}`, fields)
}

/**
 * Upload files to a session
 * @param {string} sessionId
 * @param {FormData} formData
 */
export const uploadSessionFiles = (sessionId, formData) => {
  return service.post(`/api/session/${sessionId}/files`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/**
 * Get signed download URL for a session file
 * @param {string} sessionId
 * @param {string} filename
 */
export const getSessionFileUrl = (sessionId, filename) => {
  return service.get(`/api/session/${sessionId}/files/${encodeURIComponent(filename)}`)
}

/**
 * Start deep research within a session (free if retrying)
 * @param {string} sessionId
 * @param {Object} [angleOverrides]
 */
export const startSessionResearch = (sessionId, angleOverrides) => {
  const body = {}
  if (angleOverrides && Object.keys(angleOverrides).length > 0) {
    body.angle_overrides = angleOverrides
  }
  return service.post(`/api/session/${sessionId}/research`, body)
}

/**
 * Poll session research status
 * @param {string} sessionId
 */
export const getSessionResearchStatus = (sessionId) => {
  return service.get(`/api/session/${sessionId}/research/status`)
}

/**
 * Abandon a session (no refund)
 * @param {string} sessionId
 */
export const abandonSession = (sessionId) => {
  return service.post(`/api/session/${sessionId}/abandon`)
}

/**
 * Check if user can run research (has research credits)
 */
export const canResearch = () => {
  return service.get('/api/billing/can-research')
}

/**
 * Buy research credits via Stripe checkout
 * @param {'research_1'|'research_5'} product
 * @param {string} [sessionId] - Optional session ID for return URL
 */
export const buyResearchCredits = (product, sessionId) => {
  return service.post('/api/billing/checkout', { product, session_id: sessionId || '' })
}

