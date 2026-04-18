import service, { requestWithRetry } from './index'

/**
 * Generate ontology (upload documents and simulation requirements)
 * @param {Object} data - Contains files, simulation_requirement, project_name, etc.
 * @returns {Promise}
 */
export function generateOntology(formData) {
  return requestWithRetry(() => 
    service({
      url: '/api/graph/ontology/generate',
      method: 'post',
      data: formData,
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  )
}

/**
 * Build graph
 * @param {Object} data - Contains project_id, graph_name, etc.
 * @returns {Promise}
 */
export function buildGraph(data) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/build',
      method: 'post',
      data
    })
  )
}

/**
 * Query task status
 * @param {String} taskId - Task ID
 * @returns {Promise}
 */
export function getTaskStatus(taskId) {
  return service({
    url: `/api/graph/task/${taskId}`,
    method: 'get'
  })
}

/**
 * Get graph data
 * @param {String} graphId - Graph ID
 * @param {{ refresh?: boolean }} [options] - refresh=true bypasses server snapshot cache (re-fetch from Zep)
 * @returns {Promise}
 */
export function getGraphData(graphId, options = {}) {
  const params = new URLSearchParams()
  if (options.refresh) params.set('refresh', 'true')
  const q = params.toString()
  return service({
    url: `/api/graph/data/${graphId}${q ? `?${q}` : ''}`,
    method: 'get'
  })
}

/**
 * Get project info
 * @param {String} projectId - Project ID
 * @returns {Promise}
 */
export function getProject(projectId) {
  return service({
    url: `/api/graph/project/${projectId}`,
    method: 'get'
  })
}
