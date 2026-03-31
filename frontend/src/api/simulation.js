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
 */
export const startDeepResearch = (scenario) => {
  return service.post('/api/source/deep-research', { prompt: scenario })
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

