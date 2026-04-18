<template>
  <div class="main-view">
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <div class="brand" @click="router.push('/')">GLAS</div>
      </div>
      
      <div class="header-center">
        <div class="view-switcher">
          <button 
            v-for="mode in ['graph', 'split', 'workbench']" 
            :key="mode"
            class="switch-btn"
            :class="{ active: viewMode === mode }"
            @click="viewMode = mode"
          >
            {{ { graph: 'Graph', split: 'Split', workbench: 'Workbench' }[mode] }}
          </button>
        </div>
      </div>

      <div class="header-right">
        <div class="workflow-step">
          <span class="step-num">Step {{ currentStep }}/5</span>
          <span class="step-name">{{ stepNames[currentStep - 1] }}</span>
        </div>
        <div class="step-divider"></div>
        <span class="status-indicator" :class="statusClass">
          <span class="dot"></span>
          {{ statusText }}
        </span>
      </div>
    </header>

    <!-- Main Content Area -->
    <main class="content-area">
      <!-- Left Panel: Graph -->
      <div class="panel-wrapper left" :style="leftPanelStyle">
        <GraphPanel 
          :graphData="graphData"
          :loading="graphLoading || graphRefreshing"
          :currentPhase="currentPhase"
          :graph-load-error="graphLoadError"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </div>

      <!-- Right Panel: Step Components -->
      <div class="panel-wrapper right" :style="rightPanelStyle">
        <!-- Step 1: Knowledge Graph -->
        <Step1GraphBuild 
          v-if="currentStep === 1"
          :currentPhase="currentPhase"
          :projectData="projectData"
          :ontologyProgress="ontologyProgress"
          :buildProgress="buildProgress"
          :graphData="graphData"
          :systemLogs="systemLogs"
          :bundleData="bundleData"
          @next-step="handleNextStep"
        />
        <!-- Step 2: Environment Setup -->
        <Step2EnvSetup
          v-else-if="currentStep === 2"
          :projectData="projectData"
          :graphData="graphData"
          :systemLogs="systemLogs"
          @go-back="handleGoBack"
          @next-step="handleNextStep"
          @add-log="addLog"
        />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GraphPanel from '../components/GraphPanel.vue'
import Step1GraphBuild from '../components/Step1GraphBuild.vue'
import Step2EnvSetup from '../components/Step2EnvSetup.vue'
import { generateOntology, getProject, buildGraph, getTaskStatus, getGraphData } from '../api/graph'
import { getGraphPollIntervalMs, graphSkipPollWhenDocumentHidden } from '../config/zepFootprint'
import { getPendingUpload, clearPendingUpload } from '../store/pendingUpload'
import { getSession, getSessionFileUrl, updateSession } from '../api/simulation'

const route = useRoute()
const router = useRouter()

// Layout State
const viewMode = ref('split') // graph | split | workbench

// Step State
const currentStep = ref(1) // 1: Knowledge Graph, 2: Environment Setup, 3: Run Simulation, 4: Report Generation, 5: Deep Interaction
const MAX_IMPLEMENTED_STEP = 2 // template only mounts Step1 + Step2; higher steps via ?step= would leave panel empty
const stepNames = ['Knowledge Graph', 'Environment Setup', 'Run Simulation', 'Report Generation', 'Deep Interaction']

// Data State
const currentProjectId = ref(route.params.projectId)
const loading = ref(false)
const graphLoading = ref(false)
const graphRefreshing = ref(false)
const error = ref('')
const projectData = ref(null)
const graphData = ref(null)
const graphLoadError = ref('')
const currentPhase = ref(-1) // -1: Upload, 0: Ontology, 1: Build, 2: Complete
const ontologyProgress = ref(null)
const buildProgress = ref(null)
const systemLogs = ref([])
const bundleData = ref(null)

// Polling timers
let pollTimer = null
let graphPollActive = false
let graphPollTimeoutId = null

// --- Computed Layout Styles ---
const leftPanelStyle = computed(() => {
  if (viewMode.value === 'graph') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'workbench') return { width: '0%', opacity: 0, transform: 'translateX(-20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

const rightPanelStyle = computed(() => {
  if (viewMode.value === 'workbench') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'graph') return { width: '0%', opacity: 0, transform: 'translateX(20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

// --- Status Computed ---
const statusClass = computed(() => {
  if (error.value) return 'error'
  if (currentPhase.value >= 2) return 'completed'
  return 'processing'
})

const statusText = computed(() => {
  if (error.value) return 'Error'
  if (currentPhase.value >= 2) return 'Ready'
  if (currentPhase.value === 1) return 'Building Graph'
  if (currentPhase.value === 0) return 'Generating Ontology'
  return 'Initializing'
})

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  // Keep last 100 logs
  if (systemLogs.value.length > 100) {
    systemLogs.value.shift()
  }
}

// --- Layout Methods ---
const toggleMaximize = (target) => {
  if (viewMode.value === target) {
    viewMode.value = 'split'
  } else {
    viewMode.value = target
  }
}

const handleNextStep = (params = {}) => {
  if (currentStep.value < 5) {
    currentStep.value++
    addLog(`Enter Step ${currentStep.value}: ${stepNames[currentStep.value - 1]}`)
    
    // If entering Step 3 from Step 2, log the simulation rounds config
    if (currentStep.value === 3 && params.maxRounds) {
      addLog(`Custom simulation rounds: ${params.maxRounds} rounds`)
    }
  }
}

const handleGoBack = () => {
  if (currentStep.value > 1) {
    currentStep.value--
    addLog(`Return to Step ${currentStep.value}: ${stepNames[currentStep.value - 1]}`)
  }
}

/** e.g. ?step=1 from bundle results → show Knowledge Graph / ontology panel */
function applyRouteStepQuery() {
  const raw = route.query.step
  if (raw === undefined || raw === null || raw === '') return
  const s = Array.isArray(raw) ? raw[0] : raw
  const n = parseInt(String(s), 10)
  if (Number.isNaN(n) || n < 1 || n > MAX_IMPLEMENTED_STEP) return
  if (currentStep.value !== n) {
    currentStep.value = n
    addLog(`Step ${n} (from link): ${stepNames[n - 1]}`)
  }
}

// --- Data Logic ---

const initProject = async () => {
  addLog('Project view initialized.')
  if (currentProjectId.value === 'new') {
    await handleNewProject()
  } else {
    await loadProject()
  }
}

const handleNewProject = async () => {
  const pending = getPendingUpload()
  let files = pending.files || []

  if (pending.recoveredFromStorage && files.length === 0) {
    addLog('Session recovered after refresh — downloading files from session...')
    const sessionId = localStorage.getItem('glas_active_session') || route.query.session_id
    if (sessionId) {
      try {
        const sess = await getSession(sessionId)
        const uploadedFiles = sess?.data?.uploaded_files || []
        for (const meta of uploadedFiles) {
          const urlRes = await getSessionFileUrl(sessionId, meta.name)
          if (urlRes?.data?.url) {
            const resp = await fetch(urlRes.data.url)
            const blob = await resp.blob()
            files.push(new File([blob], meta.name, { type: meta.content_type || 'application/octet-stream' }))
          }
        }
        addLog(`Recovered ${files.length} file(s) from session ${sessionId}`)
      } catch (e) {
        addLog(`Failed to recover files from session: ${e.message}`)
      }
    }
  }

  if (!pending.isPending || files.length === 0) {
    error.value = 'No pending files found.'
    addLog('Error: No pending files found for new project.')
    return
  }
  
  try {
    loading.value = true
    currentPhase.value = 0
    ontologyProgress.value = { message: 'Uploading and analyzing docs...' }
    addLog('Starting ontology generation: Uploading files...')
    
    const formData = new FormData()
    files.forEach(f => formData.append('files', f))
    formData.append('simulation_requirement', pending.simulationRequirement)
    if (pending.decisionIntake) {
      formData.append('decision_intake', JSON.stringify(pending.decisionIntake))
    }
    if (pending.researchDossier) {
      formData.append('research_dossier', JSON.stringify(pending.researchDossier))
    }
    
    if (pending.bundleData) {
      bundleData.value = pending.bundleData
      addLog(`Bundle mode: ${pending.bundleData.scenarios?.length || 0} scenarios`)
    }

    const res = await generateOntology(formData)
    if (res.success) {
      clearPendingUpload()
      currentProjectId.value = res.data.project_id
      projectData.value = res.data

      const rawSessionId = localStorage.getItem('glas_active_session') || route.query.session_id
      const currentSessionId = Array.isArray(rawSessionId) ? rawSessionId[0] : rawSessionId
      if (currentSessionId) {
        updateSession(currentSessionId, { project_id: res.data.project_id }).catch(() => {})
      }
      router.replace({
        name: 'Process',
        params: { projectId: res.data.project_id },
        query: {
          ...route.query,
          ...(currentSessionId ? { session_id: String(currentSessionId) } : {}),
        },
      })
      ontologyProgress.value = null
      addLog(`Ontology generated successfully for project ${res.data.project_id}`)
      await startBuildGraph()
    } else {
      error.value = res.error || 'Ontology generation failed'
      addLog(`Error generating ontology: ${error.value}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception in handleNewProject: ${err.message}`)
  } finally {
    loading.value = false
  }
}

const loadProject = async () => {
  try {
    loading.value = true
    addLog(`Loading project ${currentProjectId.value}...`)
    const res = await getProject(currentProjectId.value)
    if (res.success) {
      projectData.value = res.data
      updatePhaseByStatus(res.data.status)
      addLog(`Project loaded. Status: ${res.data.status}`)

      if (!bundleData.value) {
        const sessionId = localStorage.getItem('glas_active_session') || route.query.session_id
        if (sessionId) {
          try {
            const sessRes = await getSession(sessionId)
            const bc = sessRes?.data?.bundle_config
            if (bc && bc.full_analysis && bc.bundle_id) {
              bundleData.value = { bundleId: bc.bundle_id, scenarios: bc.scenarios || [] }
              addLog(`Bundle mode restored: ${bc.scenarios?.length || 0} scenarios`)
            }
          } catch { /* non-critical */ }
        }
      }

      if (res.data.status === 'ontology_generated' && !res.data.graph_id) {
        await startBuildGraph()
      } else if (res.data.status === 'graph_building' && res.data.graph_build_task_id) {
        currentPhase.value = 1
        startPollingTask(res.data.graph_build_task_id)
        startGraphPolling()
      } else if (res.data.status === 'graph_completed' && res.data.graph_id) {
        currentPhase.value = 2
        await loadGraph(res.data.graph_id)
      }
    } else {
      error.value = res.error
      addLog(`Error loading project: ${res.error}`)
    }
    applyRouteStepQuery()
  } catch (err) {
    error.value = err.message
    addLog(`Exception in loadProject: ${err.message}`)
  } finally {
    loading.value = false
  }
}

const updatePhaseByStatus = (status) => {
  switch (status) {
    case 'created':
    case 'ontology_generated': currentPhase.value = 0; break;
    case 'graph_building': currentPhase.value = 1; break;
    case 'graph_completed': currentPhase.value = 2; break;
    case 'failed': error.value = 'Project failed'; break;
  }
}

const startBuildGraph = async () => {
  try {
    currentPhase.value = 1
    buildProgress.value = { progress: 0, message: 'Starting build...' }
    addLog('Initiating graph build...')
    
    const res = await buildGraph({ project_id: currentProjectId.value })
    if (res.success) {
      addLog(`Graph build task started. Task ID: ${res.data.task_id}`)
      startGraphPolling()
      startPollingTask(res.data.task_id)
    } else {
      error.value = res.error
      addLog(`Error starting build: ${res.error}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception in startBuildGraph: ${err.message}`)
  }
}

let graphBackoffUntil = 0

const graphBuildingActive = () =>
  currentPhase.value === 1 || projectData.value?.status === 'graph_building'

const startGraphPolling = () => {
  addLog('Started polling for graph data...')
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

const fetchGraphData = async () => {
  if (graphSkipPollWhenDocumentHidden && document.hidden) return
  if (Date.now() < graphBackoffUntil) return
  try {
    let graphId = projectData.value?.graph_id
    if (!graphId) {
      const projRes = await getProject(currentProjectId.value)
      if (projRes.success && projRes.data) {
        projectData.value = projRes.data
        graphId = projRes.data.graph_id
      }
    }
    if (!graphId) return

    const gRes = await getGraphData(graphId)
    if (gRes.success) {
      graphBackoffUntil = 0
      graphLoadError.value = ''
      graphData.value = gRes.data
      const nodeCount = gRes.data.node_count || gRes.data.nodes?.length || 0
      const edgeCount = gRes.data.edge_count || gRes.data.edges?.length || 0
      addLog(`Graph data refreshed. Nodes: ${nodeCount}, Edges: ${edgeCount}`)
    }
  } catch (err) {
    const status = err.response?.status
    if (status === 429) {
      const raSec = Number.parseInt(err.response?.headers?.['retry-after'] || '60', 10)
      const backoffSec = Number.isFinite(raSec) && raSec > 0 ? raSec : 60
      const clamped = Math.min(Math.max(backoffSec, 1), 300)
      graphBackoffUntil = Date.now() + clamped * 1000
      addLog(`Graph rate limited — backing off ~${clamped}s (server cache reduces repeat calls)`)
    }
    const detail = err.response?.data?.detail || err.response?.data?.error || err.message
    graphLoadError.value = String(detail)
    console.warn('Graph fetch error:', err)
  }
}

const startPollingTask = (taskId) => {
  pollTaskStatus(taskId)
  pollTimer = setInterval(() => pollTaskStatus(taskId), 2000)
}

const pollTaskStatus = async (taskId) => {
  try {
    const res = await getTaskStatus(taskId)
    if (res.success) {
      const task = res.data
      
      // Log progress message if it changed
      if (task.message && task.message !== buildProgress.value?.message) {
        addLog(task.message)
      }
      
      buildProgress.value = { progress: task.progress || 0, message: task.message }
      
      if (task.status === 'completed') {
        addLog('Graph build task completed.')
        stopPolling()
        stopGraphPolling() // Stop polling, do final load
        currentPhase.value = 2
        
        // Final load
        const projRes = await getProject(currentProjectId.value)
        if (projRes.success && projRes.data.graph_id) {
            projectData.value = projRes.data
            await loadGraph(projRes.data.graph_id)
        }
      } else if (task.status === 'failed') {
        stopPolling()
        error.value = task.error
        addLog(`Graph build task failed: ${task.error}`)
      }
    }
  } catch (e) {
    console.error(e)
  }
}

const loadGraph = async (graphId, options = {}) => {
  graphLoading.value = true
  graphLoadError.value = ''
  addLog(`Loading full graph data: ${graphId}`)
  try {
    const res = await getGraphData(graphId, { refresh: !!options.refresh })
    if (res.success) {
      graphData.value = res.data
      addLog('Graph data loaded successfully.')
    } else {
      const msg = res.error || 'Unknown error'
      graphLoadError.value = msg
      addLog(`Failed to load graph data: ${msg}`)
    }
  } catch (e) {
    const detail = e.response?.data?.detail || e.response?.data?.error || e.message
    graphLoadError.value = String(detail)
    addLog(`Exception loading graph: ${detail}`)
  } finally {
    graphLoading.value = false
  }
}

const refreshGraph = async () => {
  if (!projectData.value?.graph_id) return
  if (graphRefreshing.value) return
  graphRefreshing.value = true
  try {
    addLog('Manual graph refresh triggered (bypasses server cache).')
    await loadGraph(projectData.value.graph_id, { refresh: true })
  } finally {
    graphRefreshing.value = false
  }
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const stopGraphPolling = () => {
  graphPollActive = false
  if (graphPollTimeoutId !== null) {
    clearTimeout(graphPollTimeoutId)
    graphPollTimeoutId = null
  }
  addLog('Graph polling stopped.')
}

const onGraphVisibilityChange = () => {
  if (!document.hidden && graphPollActive) {
    fetchGraphData()
  }
}

watch(
  () => route.query.step,
  () => {
    if (!loading.value && currentProjectId.value && currentProjectId.value !== 'new') {
      applyRouteStepQuery()
    }
  },
)

watch(
  () => route.params.projectId,
  () => {
    graphLoadError.value = ''
  },
)

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

<style scoped>
.main-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #FFF;
  overflow: hidden;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* Header */
.app-header {
  height: 60px;
  border-bottom: 1px solid #EAEAEA;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #FFF;
  z-index: 100;
  position: relative;
}

.header-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.brand {
  font-family: 'Inter', sans-serif;
  font-weight: 800;
  font-size: 18px;
  letter-spacing: 0.2em;
  cursor: pointer;
}

.view-switcher {
  display: flex;
  background: #F5F5F5;
  padding: 4px;
  border-radius: 6px;
  gap: 4px;
}

.switch-btn {
  border: none;
  background: transparent;
  padding: 6px 16px;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.switch-btn.active {
  background: #FFF;
  color: #000;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.workflow-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  color: #999;
}

.step-name {
  font-weight: 700;
  color: #000;
}

.step-divider {
  width: 1px;
  height: 14px;
  background-color: #E0E0E0;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #CCC;
}

.status-indicator.processing .dot { background: #FF5722; animation: pulse 1s infinite; }
.status-indicator.completed .dot { background: #4CAF50; }
.status-indicator.error .dot { background: #F44336; }

@keyframes pulse { 50% { opacity: 0.5; } }

/* Content */
.content-area {
  flex: 1;
  display: flex;
  position: relative;
  overflow: hidden;
}

.panel-wrapper {
  height: 100%;
  overflow: hidden;
  transition: width 0.4s cubic-bezier(0.25, 0.8, 0.25, 1), opacity 0.3s ease, transform 0.3s ease;
  will-change: width, opacity, transform;
}

.panel-wrapper.left {
  border-right: 1px solid #EAEAEA;
}
</style>
