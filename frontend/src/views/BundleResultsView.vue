<template>
  <div class="bundle-results-view">
    <header class="bundle-header">
      <div class="header-left">
        <div class="brand" @click="router.push('/home')">GLAS</div>
        <button class="nav-btn" @click="router.push('/home')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
          Home
        </button>
        <button
          v-if="workspaceProjectId"
          type="button"
          class="nav-btn"
          title="Open Step 1: ontology and knowledge graph for this project"
          @click="goToOntologyWorkspace"
        >
          Ontology &amp; graph
        </button>
      </div>
      <div class="header-center">
        <span class="bundle-title-text">{{ bundleTitle || 'Full Decision Analysis' }}</span>
      </div>
      <div class="header-right">
        <span class="status-indicator" :class="overallStatusClass">
          <span class="dot"></span>
          {{ overallStatusText }}
        </span>
      </div>
    </header>

    <main
      class="bundle-main"
      :class="{ 'has-sidebar': status?.status === 'running', 'has-comparison': isComparisonVisible }"
    >
      <div class="bundle-progress-section" v-if="status?.status === 'running'">
        <div class="progress-card">
          <div class="progress-header">
            <span class="progress-label">Running Full Analysis</span>
            <span class="progress-counter">{{ status.completed }}/{{ status.total }} completed</span>
          </div>
          <div class="progress-meta">
            <span class="elapsed-timer" v-if="elapsedText">{{ elapsedText }} elapsed</span>
            <span class="estimate-label">{{ estimatedTimeText }}</span>
          </div>
          <div class="progress-bar-outer">
            <div class="progress-bar-inner" :style="{ width: progressPercent + '%' }"></div>
          </div>
          <div class="scenario-status-list">
            <div v-for="sc in status.scenarios" :key="sc.index" class="scenario-status-row" :class="sc.status">
              <span class="sc-icon">
                <span v-if="sc.status === 'completed'" class="check">&#10003;</span>
                <span v-else-if="sc.status === 'running'" class="spinner-inline"></span>
                <span v-else-if="sc.status === 'failed'" class="fail-x">&times;</span>
                <span v-else class="pending-dash">&mdash;</span>
              </span>
              <span class="sc-title">{{ sc.title }}</span>
              <button
                v-if="sc.simulation_id"
                type="button"
                class="sc-sim-link"
                :aria-label="`Open simulation for ${sc.title}`"
                @click="goToSimulation(sc.simulation_id)"
              >
                Graph &amp; timeline
              </button>
              <span v-else-if="sc.status === 'pending'" class="sc-sim-pending" title="Starts after previous scenarios">Soon</span>
              <span class="sc-estimate" v-if="sc.status === 'pending' || sc.status === 'running'">~{{ scenarioEstimate(sc) }} min</span>
              <span class="sc-status-label">{{ sc.status.toUpperCase() }}</span>
            </div>

            <!-- Live sub-progress for the running scenario -->
            <div v-if="simProgress && runningScenarioIndex !== null" class="sim-progress-detail">
              <div class="sim-phase-label">
                <span class="phase-icon">
                  <span class="spinner-inline small"></span>
                </span>
                <span>{{ simProgressLabel }}</span>
              </div>

              <div v-if="simProgress.entities_count" class="sim-stats-row">
                <span class="sim-stat">
                  <span class="sim-stat-val">{{ simProgress.entities_count }}</span> agents
                </span>
                <span v-if="simProgress.profiles_count" class="sim-stat">
                  <span class="sim-stat-val">{{ simProgress.profiles_count }}</span> profiles
                </span>
              </div>

              <div v-if="runProgress" class="sim-run-detail">
                <div class="run-progress-bar-outer">
                  <div class="run-progress-bar-inner" :style="{ width: (runProgress.progress_percent || 0) + '%' }"></div>
                </div>
                <div class="sim-stats-row">
                  <span class="sim-stat" v-if="runProgress.current_round">
                    Round <span class="sim-stat-val">{{ runProgress.current_round }}</span> / {{ runProgress.total_rounds }}
                  </span>
                  <span class="sim-stat" v-if="runProgress.twitter_actions_count">
                    Twitter: <span class="sim-stat-val">{{ runProgress.twitter_actions_count }}</span>
                  </span>
                  <span class="sim-stat" v-if="runProgress.reddit_actions_count">
                    Reddit: <span class="sim-stat-val">{{ runProgress.reddit_actions_count }}</span>
                  </span>
                </div>
                <div v-if="runProgress.current_time_label" class="sim-time-label">
                  Simulated time: {{ runProgress.current_time_label }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <aside class="explainer-sidebar" v-if="status?.status === 'running'">
        <h4 class="explainer-title">How it works</h4>
        <div class="explainer-steps">
          <div class="explainer-step" :class="{ active: currentPhase === 'profiles' }">
            <div class="step-num">1</div>
            <div class="step-body">
              <div class="step-heading">Entity Extraction</div>
              <p>Agents are identified from your knowledge graph &mdash; real organisations, leaders, and groups relevant to the scenario.</p>
            </div>
          </div>
          <div class="explainer-step" :class="{ active: currentPhase === 'profiles' }">
            <div class="step-num">2</div>
            <div class="step-body">
              <div class="step-heading">Profile Generation</div>
              <p>Each agent gets a detailed persona: communication style, stance, allegiances, and behavioural patterns grounded in real-world data.</p>
            </div>
          </div>
          <div class="explainer-step" :class="{ active: currentPhase === 'running' }">
            <div class="step-num">3</div>
            <div class="step-body">
              <div class="step-heading">Simulation</div>
              <p>Agents interact across simulated social platforms over a compressed timeframe, reacting to events and each other.</p>
            </div>
          </div>
        </div>
        <div class="explainer-note">
          <div class="note-heading">Why do times vary?</div>
          <p>The <strong>first scenario</strong> takes longest because every agent profile must be generated from scratch. <strong>Subsequent scenarios</strong> reuse these profiles with a different scenario prompt, so only the simulation step runs &mdash; cutting the time roughly in half.</p>
        </div>
      </aside>

      <div class="bundle-comparison-section" v-if="status?.status === 'completed' || status?.status === 'completed_with_errors'">
        <BundleSynthesis
          v-if="comparison?.synthesis"
          :bundle-id="bundleId"
          :synthesis="comparison.synthesis"
          :scenarios="comparison.scenarios || []"
          @updated="onSynthesisUpdated"
        />
        <div class="comparison-header">
          <h2>Scenario Comparison</h2>
          <p v-if="comparisonContextTeaser" class="comparison-context">{{ comparisonContextTeaser }}</p>
          <span class="comparison-count">{{ comparison?.completed_count || 0 }} scenarios analyzed</span>
        </div>

        <div class="comparison-grid">
          <article
            v-for="sc in comparison?.scenarios || []"
            :key="sc.scenario_index"
            class="comparison-card"
          >
            <div class="comp-card-header">
              <span class="comp-idx">{{ sc.scenario_index + 1 }}</span>
              <div class="comp-title-block">
                <span class="comp-title">{{ sc.title }}</span>
                <p v-if="sc.change_summary" class="comp-change">{{ sc.change_summary }}</p>
              </div>
              <span class="comp-status" :class="sc.status">{{ sc.status }}</span>
            </div>
            <div class="comp-card-body">
              <div class="comp-metrics">
                <div class="comp-metric">
                  <span class="metric-label">Rounds</span>
                  <span class="metric-value">{{ formatComparisonRounds(sc) }}</span>
                </div>
                <div class="comp-metric">
                  <span class="metric-label">Actions</span>
                  <span class="metric-value">{{ formatComparisonActions(sc) }}</span>
                </div>
                <div v-if="sc.final_state?.entities_count" class="comp-metric">
                  <span class="metric-label">Agents</span>
                  <span class="metric-value">{{ sc.final_state.entities_count }}</span>
                </div>
              </div>
              <div class="comp-platforms" aria-label="Platforms">
                <span
                  class="plat-pill"
                  :class="{ done: sc.final_state?.twitter_completed }"
                >Plaza</span>
                <span
                  class="plat-pill"
                  :class="{ done: sc.final_state?.reddit_completed }"
                >Community</span>
              </div>
              <div class="comp-actions">
                <button v-if="sc.report_id" type="button" class="comp-btn" @click="viewReport(sc.report_id)">
                  View Report
                </button>
                <button
                  v-if="sc.simulation_id"
                  type="button"
                  class="comp-btn secondary"
                  @click="goToSimulation(sc.simulation_id)"
                >
                  Timeline &amp; graph
                </button>
              </div>
            </div>
          </article>
        </div>
      </div>

      <div class="bundle-error" v-if="status?.status === 'failed' || status?.status === 'error'">
        <div class="error-card">
          <h3>Analysis Failed</h3>
          <p>{{ status.error || 'An error occurred during the analysis.' }}</p>
          <button class="retry-btn" @click="router.push('/home')">Return Home</button>
        </div>
      </div>

      <div class="bundle-loading" v-if="!status">
        <div class="loading-spinner"></div>
        <span>Loading analysis status...</span>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { getBundleStatus, getBundleComparison, getSimulation, getRunStatus } from '../api/simulation'

const router = useRouter()

const props = defineProps({
  bundleId: { type: String, required: true },
})

const status = ref(null)
const comparison = ref(null)
const bundleTitle = ref('')
const simProgress = ref(null)
const runProgress = ref(null)
const bundleStartedAt = ref(null)
const elapsedSeconds = ref(0)
/** Resolved from a bundle scenario simulation — used to return to Step 1 (ontology / graph). */
const workspaceProjectId = ref(null)
let pollTimer = null
let elapsedTimer = null

const progressPercent = computed(() => {
  if (!status.value) return 0
  return status.value.total > 0 ? Math.round((status.value.completed / status.value.total) * 100) : 0
})

const isComparisonVisible = computed(
  () => status.value?.status === 'completed' || status.value?.status === 'completed_with_errors',
)

const comparisonContextTeaser = computed(() => {
  const raw = comparison.value?.decision_context
  if (!raw || typeof raw !== 'string') return ''
  const t = raw.trim()
  if (!t) return ''
  const max = 220
  return t.length > max ? `${t.slice(0, max).trim()}…` : t
})

function formatComparisonRounds(sc) {
  const fs = sc?.final_state
  if (!fs) return '—'
  const done = fs.rounds_completed ?? fs.total_rounds ?? 0
  const planned = fs.rounds_planned ?? 0
  if (planned > 0) return `${done} / ${planned}`
  if (done > 0) return String(done)
  return '—'
}

function formatComparisonActions(sc) {
  const n = sc?.final_state?.total_actions
  if (n == null || Number(n) === 0) return '—'
  return Number(n).toLocaleString()
}

const runningScenarioIndex = computed(() => {
  if (!status.value?.scenarios) return null
  const running = status.value.scenarios.find(s => s.status === 'running')
  return running ? running.index : null
})

const runningSimulationId = computed(() => {
  if (!status.value?.scenarios) return null
  const running = status.value.scenarios.find(s => s.status === 'running')
  return running?.simulation_id || null
})

const simProgressLabel = computed(() => {
  if (!simProgress.value) return 'Starting...'
  const s = simProgress.value.status
  if (s === 'created') return 'Initialising simulation...'
  if (s === 'preparing') {
    if (simProgress.value.profiles_count > 0)
      return `Generating profiles (${simProgress.value.profiles_count}/${simProgress.value.entities_count || '?'})...`
    if (simProgress.value.entities_count > 0)
      return `Found ${simProgress.value.entities_count} entities, generating profiles...`
    return 'Reading entities from graph...'
  }
  if (s === 'ready') return 'Preparation complete, starting simulation...'
  if (s === 'running') return 'Simulation running'
  if (s === 'completed') return 'Scenario complete'
  if (s === 'failed') return 'Scenario failed'
  return s || 'Processing...'
})

const overallStatusClass = computed(() => {
  const s = status.value?.status
  if (s === 'running') return 'processing'
  if (s === 'completed') return 'completed'
  if (s === 'completed_with_errors') return 'warning'
  if (s === 'failed' || s === 'error') return 'error'
  return 'processing'
})

const overallStatusText = computed(() => {
  const s = status.value?.status
  if (s === 'running') return `Running ${status.value.completed}/${status.value.total}`
  if (s === 'completed') return 'Analysis Complete'
  if (s === 'completed_with_errors') return 'Completed with errors'
  if (s === 'failed' || s === 'error') return 'Failed'
  return 'Loading...'
})

const PREP_MIN_FIRST = 18
const PREP_MIN_SHARED = 3
const SIM_MIN = 15

function formatMinutes(m) {
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const r = m % 60
  return r > 0 ? `${h}h ${r}m` : `${h}h`
}

const estimatedTimeText = computed(() => {
  if (!status.value) return ''
  const total = status.value.total || 3
  const totalMin = (PREP_MIN_FIRST + SIM_MIN) + (total - 1) * (PREP_MIN_SHARED + SIM_MIN)
  return `Est. ~${formatMinutes(totalMin)} total`
})

/** First scenario uses longer prep; /status uses 0-based `index` (see bundle.py). Supports `scenario_index` if present. */
function isFirstBundleScenario(sc) {
  if (typeof sc.index === 'number') return sc.index === 0
  if (typeof sc.scenario_index === 'number') {
    return sc.scenario_index === 0 || sc.scenario_index === 1
  }
  if (sc.index == null && sc.scenario_index == null) return true
  const n = Number(sc.scenario_index ?? sc.index)
  if (Number.isNaN(n)) return true
  return n === 0 || n === 1
}

function scenarioEstimate(sc) {
  return isFirstBundleScenario(sc) ? PREP_MIN_FIRST + SIM_MIN : PREP_MIN_SHARED + SIM_MIN
}

const currentPhase = computed(() => {
  if (!simProgress.value) return 'profiles'
  const s = simProgress.value.status
  if (s === 'running' || s === 'completed') return 'running'
  return 'profiles'
})

const elapsedText = computed(() => {
  const s = elapsedSeconds.value
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const sec = s % 60
  return sec > 0 ? `${m}m ${sec}s` : `${m}m`
})

function startElapsedTimer() {
  if (elapsedTimer) return
  elapsedTimer = setInterval(() => {
    if (!bundleStartedAt.value) return
    elapsedSeconds.value = Math.round((Date.now() - bundleStartedAt.value) / 1000)
  }, 1000)
}

function stopElapsedTimer() {
  if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null }
}

async function fetchSimProgress() {
  const simId = runningSimulationId.value
  if (!simId) {
    simProgress.value = null
    runProgress.value = null
    return
  }

  try {
    const res = await getSimulation(simId)
    const data = res.data?.data || res.data
    if (data) simProgress.value = data

    if (data?.status === 'running') {
      try {
        const runRes = await getRunStatus(simId)
        const runData = runRes.data?.data || runRes.data
        if (runData) runProgress.value = runData
      } catch {
        // getRunStatus can fail (not ready yet, network, etc.). simProgress is already updated above,
        // so runProgress may stay stale from a previous poll/scenario. If run bar freshness matters,
        // set runProgress.value = null here (tradeoff: bar hides until next successful run-status).
      }
    } else {
      runProgress.value = null
    }
  } catch {
    simProgress.value = null
    runProgress.value = null
  }
}

async function resolveWorkspaceProjectId() {
  if (workspaceProjectId.value) return
  const simIds = []
  const pushId = (id) => {
    if (id && typeof id === 'string' && !simIds.includes(id)) simIds.push(id)
  }
  for (const sc of comparison.value?.scenarios || []) {
    pushId(sc?.simulation_id)
  }
  for (const sc of status.value?.scenarios || []) {
    pushId(sc?.simulation_id)
  }
  workspaceProjectId.value = null
  for (const sid of simIds) {
    try {
      const res = await getSimulation(sid)
      const d = res?.data
      if (d?.project_id) {
        workspaceProjectId.value = d.project_id
        return
      }
    } catch {
      /* try next simulation */
    }
  }
}

async function fetchStatus() {
  try {
    const res = await getBundleStatus(props.bundleId)
    if (!res.data) {
      stopPolling()
      status.value = { status: 'error', error: 'Failed to load bundle status' }
      return
    }
    status.value = res.data
    if (!bundleTitle.value && res.data.title) bundleTitle.value = res.data.title
    if (res.data.started_at && !bundleStartedAt.value) {
      bundleStartedAt.value = new Date(res.data.started_at).getTime()
    }

    if (res.data.status === 'running') {
      await fetchSimProgress()
    } else {
      simProgress.value = null
      runProgress.value = null
    }

    await resolveWorkspaceProjectId()

    if (res.data.status === 'completed' || res.data.status === 'completed_with_errors') {
      stopPolling()
      await fetchComparison()
    } else if (res.data.status === 'failed') {
      stopPolling()
    } else if (res.data.status !== 'running') {
      stopPolling()
    }
  } catch (e) {
    console.error('Bundle status fetch error:', e)
    stopPolling()
    status.value = { status: 'failed', error: 'Could not load analysis. The bundle may not exist.' }
  }
}

async function fetchComparison() {
  try {
    const res = await getBundleComparison(props.bundleId)
    if (res.data) {
      comparison.value = res.data
      if (!bundleTitle.value && res.data.title) bundleTitle.value = res.data.title
      await resolveWorkspaceProjectId()
    }
  } catch (e) {
    console.error('Bundle comparison fetch error:', e)
  }
}

function onSynthesisUpdated(next) {
  if (!comparison.value) return
  comparison.value = {
    ...comparison.value,
    synthesis: { ...comparison.value.synthesis, ...next },
  }
}

async function startPolling() {
  await fetchStatus()
  if (status.value?.status === 'running') {
    startElapsedTimer()
    pollTimer = setInterval(fetchStatus, 5000)
  }
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  stopElapsedTimer()
}

function viewReport(reportId) {
  router.push({ name: 'Report', params: { reportId } })
}

/** Open run view; `?bundle=` enables “Back to bundle” on sim page. Auto-detect attaches to live run or loads finished results. */
function goToSimulation(simulationId) {
  router.push({
    name: 'SimulationRun',
    params: { simulationId },
    query: { bundle: props.bundleId },
  })
}

function goToOntologyWorkspace() {
  if (!workspaceProjectId.value) return
  const sessionId = typeof localStorage !== 'undefined' ? localStorage.getItem('glas_active_session') : null
  router.push({
    name: 'Process',
    params: { projectId: workspaceProjectId.value },
    query: {
      step: '1',
      ...(sessionId ? { session_id: sessionId } : {}),
    },
  })
}

onMounted(() => {
  startPolling()
})

onUnmounted(() => {
  stopPolling()
  stopElapsedTimer()
})
</script>

<style scoped src="./BundleResultsView.scoped.css"></style>
