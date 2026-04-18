<template>
  <div class="process-page">
    <nav class="navbar">
      <div class="nav-left">
        <div class="nav-brand" @click="goHome">GLAS</div>
        <button class="nav-btn" @click="goHome">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
          Dashboard
        </button>
      </div>
      
      <div class="nav-center">
        <div class="step-badge">STEP 01</div>
        <div class="step-name">Knowledge Graph</div>
      </div>

      <div class="nav-status">
        <span class="status-dot" :class="statusClass"></span>
        <span class="status-text">{{ statusText }}</span>
      </div>
    </nav>

    <div class="main-content">
      <div class="left-panel" :class="{ 'full-screen': isFullScreen }">
        <div class="panel-header">
          <div class="header-left">
            <span class="header-deco">◆</span>
            <span class="header-title">Live Knowledge Graph</span>
          </div>
          <div class="header-right">
            <template v-if="graphData">
              <span class="stat-item">{{ graphData.node_count || graphData.nodes?.length || 0 }} Nodes</span>
              <span class="stat-divider">|</span>
              <span class="stat-item">{{ graphData.edge_count || graphData.edges?.length || 0 }} Relations</span>
              <span class="stat-divider">|</span>
            </template>
            <div class="action-buttons">
                <button class="action-btn" @click="refreshGraph" :disabled="graphLoading" title="Refresh Graph">
                  <span class="icon-refresh" :class="{ 'spinning': graphLoading }">↻</span>
                </button>
                <button class="action-btn" @click="toggleFullScreen" :title="isFullScreen ? 'Exit Fullscreen' : 'Fullscreen'">
                  <span class="icon-fullscreen">{{ isFullScreen ? '↙' : '↗' }}</span>
                </button>
            </div>
          </div>
        </div>
        
        <div class="graph-container" ref="graphContainer">
          <div v-if="graphData" class="graph-view">
            <svg ref="graphSvg" class="graph-svg"></svg>
            <div v-if="currentPhase === 1" class="graph-building-hint">
              <span class="building-dot"></span>
              Updating...
            </div>
            
            <div v-if="selectedItem" class="detail-panel">
              <div class="detail-panel-header">
                <span class="detail-title">{{ selectedItem.type === 'node' ? 'Node Details' : 'Relationship' }}</span>
                <span v-if="selectedItem.type === 'node'" class="detail-badge" :style="{ background: selectedItem.color }">
                  {{ selectedItem.entityType }}
                </span>
                <button class="detail-close" @click="closeDetailPanel">×</button>
              </div>
              
              <div v-if="selectedItem.type === 'node'" class="detail-content">
                <div class="detail-row">
                  <span class="detail-label">Name:</span>
                  <span class="detail-value highlight">{{ selectedItem.data.name }}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">UUID:</span>
                  <span class="detail-value uuid">{{ selectedItem.data.uuid }}</span>
                </div>
                <div class="detail-row" v-if="selectedItem.data.created_at">
                  <span class="detail-label">Created:</span>
                  <span class="detail-value">{{ formatDate(selectedItem.data.created_at) }}</span>
                </div>
                
                
                <div class="detail-section" v-if="selectedItem.data.attributes && Object.keys(selectedItem.data.attributes).length > 0">
                  <span class="detail-label">Properties:</span>
                  <div class="properties-list">
                    <div v-for="(value, key) in selectedItem.data.attributes" :key="key" class="property-item">
                      <span class="property-key">{{ key }}:</span>
                      <span class="property-value">{{ value }}</span>
                    </div>
                  </div>
                </div>
                
                
                <div class="detail-section" v-if="selectedItem.data.summary">
                  <span class="detail-label">Summary:</span>
                  <p class="detail-summary">{{ selectedItem.data.summary }}</p>
                </div>
                
                
                <div class="detail-row" v-if="selectedItem.data.labels?.length">
                  <span class="detail-label">Labels:</span>
                  <div class="detail-labels">
                    <span v-for="label in selectedItem.data.labels" :key="label" class="label-tag">{{ label }}</span>
                  </div>
                </div>
              </div>
              
              <div v-else class="detail-content">
                <div class="edge-relation">
                  <span class="edge-source">{{ selectedItem.data.source_name || selectedItem.data.source_node_name }}</span>
                  <span class="edge-arrow">→</span>
                  <span class="edge-type">{{ selectedItem.data.name || selectedItem.data.fact_type || 'RELATED_TO' }}</span>
                  <span class="edge-arrow">→</span>
                  <span class="edge-target">{{ selectedItem.data.target_name || selectedItem.data.target_node_name }}</span>
                </div>
                
                <div class="detail-subtitle">Relationship</div>
                
                <div class="detail-row">
                  <span class="detail-label">UUID:</span>
                  <span class="detail-value uuid">{{ selectedItem.data.uuid }}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">Label:</span>
                  <span class="detail-value">{{ selectedItem.data.name || selectedItem.data.fact_type || 'RELATED_TO' }}</span>
                </div>
                <div class="detail-row" v-if="selectedItem.data.fact_type">
                  <span class="detail-label">Type:</span>
                  <span class="detail-value">{{ selectedItem.data.fact_type }}</span>
                </div>
                
                
                <div class="detail-section" v-if="selectedItem.data.fact">
                  <span class="detail-label">Fact:</span>
                  <p class="detail-summary">{{ selectedItem.data.fact }}</p>
                </div>
                
                
                <div class="detail-section" v-if="selectedItem.data.episodes?.length">
                  <span class="detail-label">Episodes:</span>
                  <div class="episodes-list">
                    <span v-for="ep in selectedItem.data.episodes" :key="ep" class="episode-tag">{{ ep }}</span>
                  </div>
                </div>
                
                <div class="detail-row" v-if="selectedItem.data.created_at">
                  <span class="detail-label">Created:</span>
                  <span class="detail-value">{{ formatDate(selectedItem.data.created_at) }}</span>
                </div>
                <div class="detail-row" v-if="selectedItem.data.valid_at">
                  <span class="detail-label">Valid From:</span>
                  <span class="detail-value">{{ formatDate(selectedItem.data.valid_at) }}</span>
                </div>
                <div class="detail-row" v-if="selectedItem.data.invalid_at">
                  <span class="detail-label">Invalid At:</span>
                  <span class="detail-value">{{ formatDate(selectedItem.data.invalid_at) }}</span>
                </div>
                <div class="detail-row" v-if="selectedItem.data.expired_at">
                  <span class="detail-label">Expired At:</span>
                  <span class="detail-value">{{ formatDate(selectedItem.data.expired_at) }}</span>
                </div>
              </div>
            </div>
          </div>
          
          <div v-else-if="graphLoading" class="graph-loading">
            <div class="loading-animation">
              <div class="loading-ring"></div>
              <div class="loading-ring"></div>
              <div class="loading-ring"></div>
            </div>
            <p class="loading-text">Loading graph data...</p>
          </div>
          
          <div v-else-if="currentPhase < 1" class="graph-waiting">
            <div class="waiting-icon">
              <svg viewBox="0 0 100 100" class="network-icon">
                <circle cx="50" cy="20" r="8" fill="none" stroke="#888" stroke-width="1.5"/>
                <circle cx="20" cy="60" r="8" fill="none" stroke="#888" stroke-width="1.5"/>
                <circle cx="80" cy="60" r="8" fill="none" stroke="#888" stroke-width="1.5"/>
                <circle cx="50" cy="80" r="8" fill="none" stroke="#888" stroke-width="1.5"/>
                <line x1="50" y1="28" x2="25" y2="54" stroke="#888" stroke-width="1"/>
                <line x1="50" y1="28" x2="75" y2="54" stroke="#888" stroke-width="1"/>
                <line x1="28" y1="60" x2="72" y2="60" stroke="#888" stroke-width="1" stroke-dasharray="4"/>
                <line x1="50" y1="72" x2="26" y2="66" stroke="#888" stroke-width="1"/>
                <line x1="50" y1="72" x2="74" y2="66" stroke="#888" stroke-width="1"/>
              </svg>
            </div>
            <p class="waiting-text">Waiting for Ontology Generation</p>
            <p class="waiting-hint">Graph build starts automatically after ontology generation</p>
          </div>
          
          <div v-else-if="currentPhase === 1 && !graphData" class="graph-waiting">
            <div class="loading-animation">
              <div class="loading-ring"></div>
              <div class="loading-ring"></div>
              <div class="loading-ring"></div>
            </div>
            <p class="waiting-text">Building Graph</p>
            <p class="waiting-hint">Data loading...</p>
          </div>
          
          <div v-else-if="error" class="graph-error">
            <span class="error-icon">⚠</span>
            <p>{{ error }}</p>
          </div>
        </div>
        
        
        <div v-if="graphData" class="graph-legend">
          <div class="legend-item" v-for="type in entityTypes" :key="type.name">
            <span class="legend-dot" :style="{ background: type.color }"></span>
            <span class="legend-label">{{ type.name }}</span>
            <span class="legend-count">{{ type.count }}</span>
          </div>
        </div>
      </div>

      <div class="right-panel" :class="{ 'hidden': isFullScreen }">
        <div class="panel-header dark-header">
          <span class="header-icon">▣</span>
          <span class="header-title">Build Process</span>
        </div>

        <div class="process-content">
          <div class="process-phase" :class="{ 'active': currentPhase === 0, 'completed': currentPhase > 0 }">
            <div class="phase-header">
              <span class="phase-num">01</span>
              <div class="phase-info">
                <div class="phase-title">Ontology Generation</div>
                <div class="phase-api">/api/graph/ontology/generate</div>
              </div>
              <span class="phase-status" :class="getPhaseStatusClass(0)">
                {{ getPhaseStatusText(0) }}
              </span>
            </div>
            
            <div class="phase-detail">
              <div class="detail-section">
                <div class="detail-label">Description</div>
                <div class="detail-content">
                  After uploading documents, the LLM analyzes content and generates ontology structure (entity types + relation types)
                </div>
              </div>
              
              <div class="detail-section" v-if="ontologyProgress && currentPhase === 0">
                <div class="detail-label">Generation Progress</div>
                <div class="ontology-progress">
                  <div class="progress-spinner"></div>
                  <span class="progress-text">{{ ontologyProgress.message }}</span>
                </div>
              </div>
              
              <div class="detail-section" v-if="projectData?.ontology">
                <div class="detail-label">Generated Entity Types ({{ projectData.ontology.entity_types?.length || 0 }})</div>
                <div class="entity-tags">
                  <span 
                    v-for="entity in projectData.ontology.entity_types" 
                    :key="entity.name"
                    class="entity-tag"
                  >
                    {{ entity.name }}
                  </span>
                </div>
              </div>
              
              <div class="detail-section" v-if="projectData?.ontology">
                <div class="detail-label">Generated Relation Types ({{ projectData.ontology.relation_types?.length || 0 }})</div>
                <div class="relation-list">
                  <div 
                    v-for="(rel, idx) in projectData.ontology.relation_types?.slice(0, 5) || []" 
                    :key="idx"
                    class="relation-item"
                  >
                    <span class="rel-source">{{ rel.source_type }}</span>
                    <span class="rel-arrow">→</span>
                    <span class="rel-name">{{ rel.name }}</span>
                    <span class="rel-arrow">→</span>
                    <span class="rel-target">{{ rel.target_type }}</span>
                  </div>
                  <div v-if="(projectData.ontology.relation_types?.length || 0) > 5" class="relation-more">
                    +{{ projectData.ontology.relation_types.length - 5 }} more relations...
                  </div>
                </div>
              </div>
              
              <div class="detail-section waiting-state" v-if="!projectData?.ontology && currentPhase === 0 && !ontologyProgress">
                <div class="waiting-hint">Waiting for ontology generation...</div>
              </div>
            </div>
          </div>

          <div class="process-phase" :class="{ 'active': currentPhase === 1, 'completed': currentPhase > 1 }">
            <div class="phase-header">
              <span class="phase-num">02</span>
              <div class="phase-info">
                <div class="phase-title">Graph Build</div>
                <div class="phase-api">/api/graph/build</div>
              </div>
              <span class="phase-status" :class="getPhaseStatusClass(1)">
                {{ getPhaseStatusText(1) }}
              </span>
            </div>
            
            <div class="phase-detail">
              <div class="detail-section">
                <div class="detail-label">Description</div>
                <div class="detail-content">
                  Build knowledge graph from ontology via Zep API, extracting entities and relations
                </div>
              </div>
              
              <div class="detail-section waiting-state" v-if="currentPhase < 1">
                <div class="waiting-hint">Waiting for ontology generation...</div>
              </div>
              
              <div class="detail-section" v-if="buildProgress && currentPhase >= 1">
                <div class="detail-label">Build Progress</div>
                <div class="progress-bar">
                  <div class="progress-fill" :style="{ width: buildProgress.progress + '%' }"></div>
                </div>
                <div class="progress-info">
                  <span class="progress-message">{{ buildProgress.message }}</span>
                  <span class="progress-percent">{{ buildProgress.progress }}%</span>
                </div>
              </div>
              
              <div class="detail-section" v-if="graphData">
                <div class="detail-label">Build Results</div>
                <div class="build-result">
                  <div class="result-item">
                    <span class="result-value">{{ graphData.node_count }}</span>
                    <span class="result-label">Entity Nodes</span>
                  </div>
                  <div class="result-item">
                    <span class="result-value">{{ graphData.edge_count }}</span>
                    <span class="result-label">Relation Edges</span>
                  </div>
                  <div class="result-item">
                    <span class="result-value">{{ entityTypes.length }}</span>
                    <span class="result-label">Entity Types</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="process-phase" :class="{ 'active': currentPhase === 2, 'completed': currentPhase > 2 }">
            <div class="phase-header">
              <span class="phase-num">03</span>
              <div class="phase-info">
                <div class="phase-title">Build Complete</div>
                <div class="phase-api">Ready for next step</div>
              </div>
              <span class="phase-status" :class="getPhaseStatusClass(2)">
                {{ getPhaseStatusText(2) }}
              </span>
            </div>
          </div>

          <div class="next-step-section" v-if="currentPhase >= 2">
            <button class="next-step-btn" @click="goToNextStep" :disabled="currentPhase < 2">
              Proceed to Environment Setup
              <span class="btn-arrow">→</span>
            </button>
          </div>
        </div>

        <div class="project-panel">
          <div class="project-header">
            <span class="project-icon">◇</span>
            <span class="project-title">Project Info</span>
          </div>
          <div class="project-details" v-if="projectData">
            <div class="project-item">
              <span class="item-label">Project Name</span>
              <span class="item-value">{{ projectData.name }}</span>
            </div>
            <div class="project-item">
              <span class="item-label">Project ID</span>
              <span class="item-value code">{{ projectData.project_id }}</span>
            </div>
            <div class="project-item" v-if="projectData.graph_id">
              <span class="item-label">Graph ID</span>
              <span class="item-value code">{{ projectData.graph_id }}</span>
            </div>
            <div class="project-item">
              <span class="item-label">Scenario</span>
              <span class="item-value">{{ projectData.simulation_requirement || '-' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectRouteId } from '../composables/useProjectRouteId'
import { generateOntology, getProject, buildGraph, getTaskStatus, getGraphData } from '../api/graph'
import { getSession } from '../api/simulation'
import { getGraphPollIntervalMs, graphSkipPollWhenDocumentHidden } from '../config/zepFootprint'
import { getPendingUpload, clearPendingUpload } from '../store/pendingUpload'
import * as d3 from 'd3'

const { route, projectId: currentProjectId } = useProjectRouteId()

function resolveLinkedSessionId() {
  const q = route.query.session_id
  if (typeof q === 'string' && q.trim()) return q.trim()
  if (typeof localStorage !== 'undefined') {
    const s = localStorage.getItem('glas_active_session')
    if (s && s.trim()) return s.trim()
  }
  return null
}

/** If disk project.json lacks graph_id, recover Zep id from Supabase session (backup column). */
async function mergeGraphIdFromSessionIfNeeded() {
  if (!projectData.value) return
  if (projectData.value.graph_id) return
  const sid = resolveLinkedSessionId()
  if (!sid) return
  try {
    const res = await getSession(sid)
    const s = res?.data
    const gid = s?.graph_id
    if (!gid || typeof gid !== 'string') return
    projectData.value = { ...projectData.value, graph_id: gid }
  } catch {
    /* session fetch failed — continue without backup graph id */
  }
}
const router = useRouter()

const loading = ref(true)
const graphLoading = ref(false)
const error = ref('')
const projectData = ref(null)
const graphData = ref(null)
const buildProgress = ref(null)
const ontologyProgress = ref(null)
const currentPhase = ref(-1)
const selectedItem = ref(null)
const isFullScreen = ref(false)

const graphContainer = ref(null)
const graphSvg = ref(null)

let pollTimer = null

const statusClass = computed(() => {
  if (error.value) return 'error'
  if (currentPhase.value >= 2) return 'completed'
  return 'processing'
})

const statusText = computed(() => {
  if (error.value) return 'Build Failed'
  if (currentPhase.value >= 2) return 'Build Complete'
  if (currentPhase.value === 1) return 'Building Graph'
  if (currentPhase.value === 0) return 'Generating Ontology'
  return 'Initializing'
})

const entityTypes = computed(() => {
  if (!graphData.value?.nodes) return []
  
  const typeMap = {}
  const colors = ['#FF6B35', '#004E89', '#7B2D8E', '#1A936F', '#C5283D', '#E9724C']
  
  graphData.value.nodes.forEach(node => {
    const type = node.labels?.find(l => l !== 'Entity') || 'Entity'
    if (!typeMap[type]) {
      typeMap[type] = { name: type, count: 0, color: colors[Object.keys(typeMap).length % colors.length] }
    }
    typeMap[type].count++
  })
  
  return Object.values(typeMap)
})

const goHome = () => {
  router.push('/')
}

const goToNextStep = () => {
  alert('Environment setup loading...')
}

const toggleFullScreen = () => {
  isFullScreen.value = !isFullScreen.value
  // Wait for transition to finish then re-render graph
  setTimeout(() => {
    renderGraph()
  }, 350) 
}

const closeDetailPanel = () => {
  selectedItem.value = null
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  try {
    const date = new Date(dateStr)
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return dateStr
  }
}

const selectNode = (nodeData, color) => {
  selectedItem.value = {
    type: 'node',
    data: nodeData,
    color: color,
    entityType: nodeData.labels?.find(l => l !== 'Entity' && l !== 'Node') || 'Entity'
  }
}

const selectEdge = (edgeData) => {
  selectedItem.value = {
    type: 'edge',
    data: edgeData
  }
}

const getPhaseStatusClass = (phase) => {
  if (currentPhase.value > phase) return 'completed'
  if (currentPhase.value === phase) return 'active'
  return 'pending'
}

const getPhaseStatusText = (phase) => {
  if (currentPhase.value > phase) return 'Completed'
  if (currentPhase.value === phase) {
    if (phase === 1 && buildProgress.value) {
      return `${buildProgress.value.progress}%`
    }
    return 'In Progress'
  }
  return 'Waiting'
}

const initProject = async () => {
  const paramProjectId = route.params.projectId
  
  if (paramProjectId === 'new') {
    await handleNewProject()
  } else {
    currentProjectId.value = paramProjectId
    await loadProject()
  }
}

const handleNewProject = async () => {
  const pending = getPendingUpload()
  
  if (!pending.isPending || pending.files.length === 0) {
    error.value = 'No files to upload. Please go back and try again.'
    loading.value = false
    return
  }
  
  try {
    loading.value = true
    currentPhase.value = 0
    ontologyProgress.value = { message: 'Uploading and analyzing documents...' }
    
    const formDataObj = new FormData()
    pending.files.forEach(file => {
      formDataObj.append('files', file)
    })
    formDataObj.append('simulation_requirement', pending.simulationRequirement)
    
    const response = await generateOntology(formDataObj)
    
    if (response.success) {
      clearPendingUpload()
      
      currentProjectId.value = response.data.project_id
      projectData.value = response.data
      
      router.replace({
        name: 'Process',
        params: { projectId: response.data.project_id }
      })
      
      ontologyProgress.value = null
      
      await startBuildGraph()
    } else {
      error.value = response.error || 'Ontology generation failed'
    }
  } catch (err) {
    console.error('Handle new project error:', err)
    error.value = 'Project initialization failed: ' + (err.message || 'Unknown')
  } finally {
    loading.value = false
  }
}

const loadProject = async () => {
  try {
    loading.value = true
    const response = await getProject(currentProjectId.value)
    
    if (response.success) {
      projectData.value = response.data
      updatePhaseByStatus(response.data.status)
      await mergeGraphIdFromSessionIfNeeded()

      const pd = projectData.value
      if (pd.status === 'ontology_generated' && !pd.graph_id) {
        await startBuildGraph()
      }

      if (pd.status === 'graph_building' && pd.graph_build_task_id) {
        currentPhase.value = 1
        startPollingTask(pd.graph_build_task_id)
        startGraphPolling()
      }

      if (pd.status === 'graph_completed' && pd.graph_id) {
        currentPhase.value = 2
        await loadGraph(pd.graph_id)
      }
    } else {
      error.value = response.error || 'Failed to load project'
    }
  } catch (err) {
    console.error('Load project error:', err)
    error.value = 'Failed to load project: ' + (err.message || 'Unknown')
  } finally {
    loading.value = false
  }
}

const updatePhaseByStatus = (status) => {
  switch (status) {
    case 'created':
    case 'ontology_generated':
      currentPhase.value = 0
      break
    case 'graph_building':
      currentPhase.value = 1
      break
    case 'graph_completed':
      currentPhase.value = 2
      break
    case 'failed':
      error.value = projectData.value?.error || 'Processing failed'
      break
  }
}

const startBuildGraph = async () => {
  try {
    currentPhase.value = 1
    buildProgress.value = {
      progress: 0,
      message: 'Starting graph build...'
    }
    
    const response = await buildGraph({ project_id: currentProjectId.value })
    
    if (response.success) {
      buildProgress.value.message = 'Graph build task started...'
      
      const taskId = response.data.task_id
      
      startGraphPolling()
      
      startPollingTask(taskId)
    } else {
      error.value = response.error || 'Failed to start graph build'
      buildProgress.value = null
    }
  } catch (err) {
    console.error('Build graph error:', err)
    error.value = 'Failed to start graph build: ' + (err.message || 'Unknown')
    buildProgress.value = null
  }
}

let graphPollActive = false
let graphPollTimeoutId = null
let graphBackoffUntil = 0

const graphBuildingActive = () =>
  currentPhase.value === 1 || projectData.value?.status === 'graph_building'

const startGraphPolling = () => {
  stopGraphPolling()
  graphPollActive = true
  scheduleGraphPoll(0)
}

const scheduleGraphPoll = (delayMs) => {
  if (!graphPollActive) return
  if (graphPollTimeoutId !== null) {
    clearTimeout(graphPollTimeoutId)
    graphPollTimeoutId = null
  }
  graphPollTimeoutId = setTimeout(async () => {
    graphPollTimeoutId = null
    if (!graphPollActive) return
    await fetchGraphData()
    if (!graphPollActive) return
    const base = getGraphPollIntervalMs({
      documentHidden: document.hidden,
      graphBuilding: graphBuildingActive(),
    })
    scheduleGraphPoll(base)
  }, delayMs)
}

const refreshGraph = async () => {
  if (!projectData.value?.graph_id) return
  graphLoading.value = true
  try {
    await loadGraph(projectData.value.graph_id, { refresh: true })
  } finally {
    graphLoading.value = false
  }
}

const stopGraphPolling = () => {
  graphPollActive = false
  if (graphPollTimeoutId !== null) {
    clearTimeout(graphPollTimeoutId)
    graphPollTimeoutId = null
  }
}

const fetchGraphData = async () => {
  if (graphSkipPollWhenDocumentHidden && document.hidden) return
  if (Date.now() < graphBackoffUntil) return
  try {
    let graphId = projectData.value?.graph_id
    if (!graphId) {
      const projectResponse = await getProject(currentProjectId.value)
      if (projectResponse.success && projectResponse.data) {
        projectData.value = projectResponse.data
        graphId = projectResponse.data.graph_id
      }
    }
    if (!graphId) return

    const graphResponse = await getGraphData(graphId)

    if (graphResponse.success && graphResponse.data) {
      graphBackoffUntil = 0
      const newData = graphResponse.data
      const newNodeCount = newData.node_count || newData.nodes?.length || 0
      const oldNodeCount = graphData.value?.node_count || graphData.value?.nodes?.length || 0

      if (newNodeCount !== oldNodeCount || !graphData.value) {
        graphData.value = newData
        await nextTick()
        renderGraph()
      }
    }
  } catch (err) {
    const status = err.response?.status
    if (status === 429) {
      const raSec = Number.parseInt(err.response?.headers?.['retry-after'] || '60', 10)
      const backoffSec = Number.isFinite(raSec) && raSec > 0 ? raSec : 60
      const clamped = Math.min(Math.max(backoffSec, 1), 300)
      graphBackoffUntil = Date.now() + clamped * 1000
    }
    console.log('Graph data fetch:', err.message || 'not ready')
  }
}

const onGraphVisibilityChange = () => {
  if (!document.hidden && graphPollActive) {
    fetchGraphData()
  }
}

const startPollingTask = (taskId) => {
  pollTaskStatus(taskId)
  
  pollTimer = setInterval(() => {
    pollTaskStatus(taskId)
  }, 2000)
}

const pollTaskStatus = async (taskId) => {
  try {
    const response = await getTaskStatus(taskId)
    
    if (response.success) {
      const task = response.data
      
      buildProgress.value = {
        progress: task.progress || 0,
        message: task.message || 'Processing...'
      }
      
      console.log('Task status:', task.status, 'Progress:', task.progress)
      
      if (task.status === 'completed') {
        console.log('Graph build complete, loading full data...')
        
        stopPolling()
        stopGraphPolling()
        currentPhase.value = 2
        
        buildProgress.value = {
          progress: 100,
          message: 'Build complete, loading graph...'
        }
        
        const projectResponse = await getProject(currentProjectId.value)
        if (projectResponse.success) {
          projectData.value = projectResponse.data
          
          if (projectResponse.data.graph_id) {
            console.log('Loading full graph:', projectResponse.data.graph_id)
            await loadGraph(projectResponse.data.graph_id)
            console.log('Graph loaded')
          }
        }
        
        buildProgress.value = null
      } else if (task.status === 'failed') {
        stopPolling()
        stopGraphPolling()
        error.value = 'Graph build failed: ' + (task.error || 'Unknown')
        buildProgress.value = null
      }
    }
  } catch (err) {
    console.error('Poll task error:', err)
  }
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const loadGraph = async (graphId, options = {}) => {
  try {
    graphLoading.value = true
    const response = await getGraphData(graphId, { refresh: !!options.refresh })
    
    if (response.success) {
      graphData.value = response.data
      await nextTick()
      renderGraph()
    }
  } catch (err) {
    console.error('Load graph error:', err)
  } finally {
    graphLoading.value = false
  }
}

const renderGraph = () => {
  if (!graphSvg.value || !graphData.value) {
    console.log('Cannot render: svg or data missing')
    return
  }
  
  const container = graphContainer.value
  if (!container) {
    console.log('Cannot render: container missing')
    return
  }
  
  const rect = container.getBoundingClientRect()
  const width = rect.width || 800
  const height = (rect.height || 600) - 60
  
  if (width <= 0 || height <= 0) {
    console.log('Cannot render: invalid dimensions', width, height)
    return
  }
  
  console.log('Rendering graph:', width, 'x', height)
  
  const svg = d3.select(graphSvg.value)
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', `0 0 ${width} ${height}`)
  
  svg.selectAll('*').remove()
  
  const nodesData = graphData.value.nodes || []
  const edgesData = graphData.value.edges || []
  
  if (nodesData.length === 0) {
    console.log('No nodes to render')
    svg.append('text')
      .attr('x', width / 2)
      .attr('y', height / 2)
      .attr('text-anchor', 'middle')
      .attr('fill', '#999')
      .text('Waiting for graph data...')
    return
  }
  
  const nodeMap = {}
  nodesData.forEach(n => {
    nodeMap[n.uuid] = n
  })
  
  const nodes = nodesData.map(n => ({
    id: n.uuid,
    name: n.name || 'Unnamed',
    type: n.labels?.find(l => l !== 'Entity' && l !== 'Node') || 'Entity',
    rawData: n
  }))
  
  const nodeIds = new Set(nodes.map(n => n.id))
  
  const edges = edgesData
    .filter(e => nodeIds.has(e.source_node_uuid) && nodeIds.has(e.target_node_uuid))
    .map(e => ({
      source: e.source_node_uuid,
      target: e.target_node_uuid,
      type: e.fact_type || e.name || 'RELATED_TO',
      rawData: {
        ...e,
        source_name: nodeMap[e.source_node_uuid]?.name || 'Unknown',
        target_name: nodeMap[e.target_node_uuid]?.name || 'Unknown'
      }
    }))
  
  console.log('Nodes:', nodes.length, 'Edges:', edges.length)
  
  const types = [...new Set(nodes.map(n => n.type))]
  const colorScale = d3.scaleOrdinal()
    .domain(types)
    .range(['#FF6B35', '#004E89', '#7B2D8E', '#1A936F', '#C5283D', '#E9724C', '#2D3436', '#6C5CE7'])
  
  const simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id(d => d.id).distance(100).strength(0.5))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(40))
    .force('x', d3.forceX(width / 2).strength(0.05))
    .force('y', d3.forceY(height / 2).strength(0.05))
  
  const g = svg.append('g')
  
  svg.call(d3.zoom()
    .extent([[0, 0], [width, height]])
    .scaleExtent([0.2, 4])
    .on('zoom', (event) => {
      g.attr('transform', event.transform)
    }))
  
  const linkGroup = g.append('g')
    .attr('class', 'links')
    .selectAll('g')
    .data(edges)
    .enter()
    .append('g')
    .style('cursor', 'pointer')
    .on('click', (event, d) => {
      event.stopPropagation()
      selectEdge(d.rawData)
    })
  
  const link = linkGroup.append('line')
    .attr('stroke', '#444')
    .attr('stroke-width', 1.5)
    .attr('stroke-opacity', 0.6)
  
  linkGroup.append('line')
    .attr('stroke', 'transparent')
    .attr('stroke-width', 10)
  
  const linkLabel = g.append('g')
    .attr('class', 'link-labels')
    .selectAll('text')
    .data(edges)
    .enter()
    .append('text')
    .attr('font-size', '9px')
    .attr('fill', '#999')
    .attr('text-anchor', 'middle')
    .text(d => d.type)
  
  const node = g.append('g')
    .attr('class', 'nodes')
    .selectAll('g')
    .data(nodes)
    .enter()
    .append('g')
    .style('cursor', 'pointer')
    .on('click', (event, d) => {
      event.stopPropagation()
      selectNode(d.rawData, colorScale(d.type))
    })
    .call(d3.drag()
      .on('start', dragstarted)
      .on('drag', dragged)
      .on('end', dragended))
  
  node.append('circle')
    .attr('r', 10)
    .attr('fill', d => colorScale(d.type))
    .attr('stroke', '#1e1e1e')
    .attr('stroke-width', 2)
    .attr('class', 'node-circle')
  
  node.append('text')
    .attr('dx', 14)
    .attr('dy', 4)
    .text(d => d.name || '')
    .attr('font-size', '11px')
    .attr('fill', '#ccc')
    .attr('font-family', 'JetBrains Mono, monospace')
  
  svg.on('click', () => {
    closeDetailPanel()
  })
  
  simulation.on('tick', () => {
    linkGroup.selectAll('line')
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y)
    
    linkLabel
      .attr('x', d => (d.source.x + d.target.x) / 2)
      .attr('y', d => (d.source.y + d.target.y) / 2 - 5)
    
    node.attr('transform', d => `translate(${d.x},${d.y})`)
  })
  
  function dragstarted(event) {
    if (!event.active) simulation.alphaTarget(0.3).restart()
    event.subject.fx = event.subject.x
    event.subject.fy = event.subject.y
  }
  
  function dragged(event) {
    event.subject.fx = event.x
    event.subject.fy = event.y
  }
  
  function dragended(event) {
    if (!event.active) simulation.alphaTarget(0)
    event.subject.fx = null
    event.subject.fy = null
  }
}

watch(graphData, () => {
  if (graphData.value) {
    nextTick(() => renderGraph())
  }
})

onMounted(() => {
  document.addEventListener('visibilitychange', onGraphVisibilityChange)
  initProject()
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onGraphVisibilityChange)
  stopPolling()
  stopGraphPolling()
})
</script>

<style scoped src="./Process.scoped.css"></style>
