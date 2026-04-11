<template>
  <div class="home-container">
    <AppNavbar />

    <div class="main-content">
      <section class="hero-section anim-fade" style="--delay: 0s">
        <div class="hero-left">
          <div class="tag-row">
            <span class="accent-tag">Multi-Agent Scenario Intelligence</span>
            <span class="version-text">/ v1.0</span>
          </div>

          <h1 class="main-title">
            Describe any scenario<br>
            <span class="gradient-text">{{ typewriterText }}<span v-if="!typewriterDone" class="tw-cursor">|</span></span>
          </h1>

          <div class="hero-desc">
            <p>
              Describe a scenario and <span class="highlight-bold">Glas Intelligence</span> guides you through gathering source materials, then creates <span class="highlight-accent">AI agents</span> who simulate stakeholder reactions over time. Discover how complex situations <span class="highlight-code">evolve</span>.
            </p>
            <p class="slogan-text">
              Scenario intelligence powered by multi-agent simulation<span class="blinking-cursor">_</span>
            </p>
          </div>

          <div class="decoration-square"></div>
        </div>

        <div class="hero-right">
          <div class="logo-container">
            <img src="../assets/logo/glas-logo.png" alt="Glas Intelligence Logo" class="hero-logo" />
          </div>
          <button class="scroll-down-btn" @click="scrollToBottom">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
        </div>
      </section>

      <section class="dashboard-section">
        <div class="left-panel anim-fade" style="--delay: .15s">
          <div class="panel-header">
            <span class="pulse-dot"></span> System Status
          </div>

          <h2 class="section-title">Ready</h2>
          <p class="section-desc">
            Prediction engine on standby. Describe a scenario to begin.
          </p>

          <div class="metrics-row">
            <div class="metric-card">
              <div class="metric-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
              </div>
              <div class="metric-value">{{ planLimits.agents }}</div>
              <div class="metric-label">Agents per simulation</div>
            </div>
            <div class="metric-card">
              <div class="metric-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
              </div>
              <div class="metric-value">{{ planLimits.rounds }}</div>
              <div class="metric-label">Decision rounds</div>
            </div>
          </div>

          <div class="steps-container">
            <div class="steps-header">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
              Workflow
            </div>
            <div class="workflow-list">
              <div class="workflow-item">
                <div class="step-icon-wrap">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
                </div>
                <div class="step-info">
                  <div class="step-title">Knowledge Graph</div>
                  <div class="step-desc">Document analysis, entity extraction, and GraphRAG construction</div>
                </div>
              </div>
              <div class="workflow-item">
                <div class="step-icon-wrap">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
                </div>
                <div class="step-info">
                  <div class="step-title">Environment Setup</div>
                  <div class="step-desc">Entity extraction, persona generation, and simulation configuration</div>
                </div>
              </div>
              <div class="workflow-item">
                <div class="step-icon-wrap">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                </div>
                <div class="step-info">
                  <div class="step-title">Run Simulation</div>
                  <div class="step-desc">Dual-platform parallel simulation with dynamic temporal memory</div>
                </div>
              </div>
              <div class="workflow-item">
                <div class="step-icon-wrap">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                </div>
                <div class="step-info">
                  <div class="step-title">Report Generation</div>
                  <div class="step-desc">Report Agent uses specialized tools to analyze simulation data</div>
                </div>
              </div>
              <div class="workflow-item">
                <div class="step-icon-wrap">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                </div>
                <div class="step-info">
                  <div class="step-title">Deep Interaction</div>
                  <div class="step-desc">Interview any simulated agent or chat with the Report Agent</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="right-panel anim-fade" style="--delay: .3s">
          <div class="console-box">
            <div class="console-section">
              <div class="console-header">
                <span class="console-label">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
                  01 / Describe Your Scenario
                </span>
                <button
                  class="enhance-btn"
                  :disabled="!formData.simulationRequirement.trim() || loading || enhancing"
                  @click="handleEnhancePrompt"
                >
                  <span v-if="!enhancing">Enhance</span>
                  <span v-else>Enhancing...</span>
                </button>
              </div>
              <div class="input-wrapper">
                <textarea
                  v-model="formData.simulationRequirement"
                  class="code-input"
                  placeholder="What happens if Ofgem removes the energy price cap? What if the US imposes new tariffs on EU goods?"
                  rows="5"
                  :disabled="loading"
                ></textarea>
                <div class="model-badge">Engine: GLAS v1.0</div>
              </div>
            </div>

            <!-- Starter Scenario Cards (shown when textarea is empty) -->
            <div v-if="!formData.simulationRequirement.trim()" class="starter-scenarios">
              <div class="starter-header">Try an example</div>
              <div class="starter-cards">
                <button
                  v-for="(ex, i) in starterExamples"
                  :key="i"
                  class="starter-card"
                  @click="formData.simulationRequirement = ex.scenario"
                >
                  <span class="starter-icon">{{ ex.icon }}</span>
                  <span class="starter-text">{{ ex.label }}</span>
                </button>
              </div>
            </div>


            <template v-if="formData.simulationRequirement.trim()">
              <div class="console-section">
                <!-- Decision Context Form -->
                <div class="console-divider inner-divider" style="margin-top: 12px;">
                  <span>Decision Context (Optional)</span>
                </div>
                <div class="decision-context-form">
                  <div class="decision-field">
                    <label class="decision-label">Your Role</label>
                    <input v-model="decisionForm.role" class="decision-input" placeholder="e.g. Head of Strategy, Portfolio Manager, Policy Analyst" />
                  </div>
                  <div class="decision-field">
                    <label class="decision-label">Decision Question</label>
                    <input v-model="decisionForm.decision" class="decision-input" placeholder="e.g. Should we proceed with the acquisition?" />
                  </div>
                  <div class="decision-field">
                    <label class="decision-label">Constraints</label>
                    <input v-model="decisionForm.constraints" class="decision-input" placeholder="e.g. Budget cap of $5M, must decide by Q3" />
                  </div>
                  <div class="decision-field">
                    <label class="decision-label">Flip Conditions</label>
                    <input v-model="decisionForm.flip_conditions" class="decision-input" placeholder="e.g. If market cap drops below $10B, reverse decision" />
                  </div>
                  <div v-if="prefillRestored" class="prefill-restored-hint">
                    ↩ Restored from previous simulation
                  </div>
                </div>

                <!-- Deep Research Button -->
                <button
                  class="auto-research-btn"
                  :class="{ disabled: !isPaidUser }"
                  :disabled="researchLoading"
                  @click="runDeepResearch"
                  :title="isPaidUser ? 'Launch deep research with AI web search' : 'Upgrade to Pro or Business to unlock deep research'"
                >
                  <span v-if="!researchLoading">
                    {{ isPaidUser ? 'Deep Research Briefing' : 'Deep Research (Paid Plans)' }}
                  </span>
                  <span v-else class="research-loading-content">
                    <span class="pulse-indicator"></span>
                    {{ researchStatusMessage }} ({{ researchElapsed }}s)
                  </span>
                </button>

                <div v-if="error" class="research-error">{{ error }}</div>

                <div v-if="briefing" class="briefing-preview">
                  <div class="briefing-header">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <span class="briefing-title">{{ briefing.filename }}</span>
                    <button class="briefing-toggle" @click="briefingExpanded = !briefingExpanded">
                      {{ briefingExpanded ? 'Collapse' : 'Read' }}
                    </button>
                    <button class="remove-btn" @click="removeBriefing">&times;</button>
                  </div>
                  <div class="briefing-content" :class="{ expanded: briefingExpanded }">{{ briefingExpanded ? briefing.content_md : briefing.content_md.slice(0, 300) + '...' }}</div>
                </div>

                <div class="console-divider inner-divider">
                  <span>Upload Additional Documents</span>
                </div>

                <div class="console-header">
                  <span class="console-label">Supported formats: PDF, MD, TXT</span>
                </div>

                <div
                  class="upload-zone"
                  :class="{ 'drag-over': isDragOver, 'has-files': files.length > 0 }"
                  @dragover.prevent="handleDragOver"
                  @dragleave.prevent="handleDragLeave"
                  @drop.prevent="handleDrop"
                  @click="triggerFileInput"
                >
                  <input
                    ref="fileInput"
                    type="file"
                    multiple
                    accept=".pdf,.md,.txt"
                    @change="handleFileSelect"
                    style="display: none"
                    :disabled="loading"
                  />

                  <div v-if="files.length === 0" class="upload-placeholder">
                    <div class="upload-icon">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    </div>
                    <div class="upload-title">Drag and drop files</div>
                    <div class="upload-hint">or click to browse</div>
                  </div>

                  <div v-else class="file-list">
                    <div v-for="(file, index) in files" :key="index" class="file-item">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>
                      <span class="file-name">{{ file.name }}</span>
                      <button @click.stop="removeFile(index)" class="remove-btn">&times;</button>
                    </div>
                  </div>
                </div>
              </div>

              <div class="console-section bundle-toggle-section" v-if="isPaidUser">
                <label class="bundle-toggle">
                  <input type="checkbox" v-model="fullAnalysisMode" />
                  <span class="bundle-toggle-label">Run Full Decision Analysis</span>
                  <span class="bundle-toggle-hint">Generates 3-5 related scenarios for a comprehensive analysis</span>
                </label>
              </div>

              <div v-if="fullAnalysisMode && bundlePlan.length > 0" class="console-section bundle-preview">
                <div class="bundle-preview-header">
                  <span class="bundle-preview-label">Analysis Plan</span>
                  <span class="bundle-preview-count">{{ bundlePlan.length }} scenarios</span>
                </div>
                <div class="bundle-preview-list">
                  <div v-for="(s, i) in bundlePlan" :key="i" class="bundle-preview-item">
                    <span class="bundle-preview-idx">{{ i + 1 }}</span>
                    <div class="bundle-preview-info">
                      <span class="bundle-preview-title">{{ s.title }}</span>
                      <span class="bundle-preview-change">{{ s.change_summary }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="fullAnalysisMode && bundleLoading" class="console-section bundle-loading">
                <div class="bundle-spinner"></div>
                <span>Generating analysis plan...</span>
              </div>

              <div class="console-section btn-section">
                <button
                  class="start-engine-btn"
                  @click="startSimulation"
                  :disabled="!canSubmit || loading"
                >
                  <span v-if="!loading">{{ fullAnalysisMode ? 'Start Full Analysis' : 'Start Engine' }}</span>
                  <span v-else>Initializing...</span>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                </button>
              </div>
            </template>
          </div>
        </div>
      </section>

      <HistoryDatabase />
    </div>

    <!-- Upgrade Modal -->
    <Teleport to="body">
      <div v-if="showUpgradeModal" class="modal-overlay" @click.self="showUpgradeModal = false">
        <div class="upgrade-modal">
          <button class="modal-close" @click="showUpgradeModal = false">&times;</button>
          <div class="modal-icon">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          </div>
          <h3 class="modal-title">Custom Simulations Require a Plan</h3>
          <p class="modal-desc">Upgrade to Pro or Business to run custom scenario simulations with AI agents, deep research, and quantified decision reports.</p>
          <div class="modal-actions">
            <button class="modal-btn primary" @click="router.push('/pricing')">View Plans</button>
            <button class="modal-btn secondary" @click="router.push('/feed')">Browse Free Reports</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import HistoryDatabase from '../components/HistoryDatabase.vue'
import AppNavbar from '../components/AppNavbar.vue'
import { authState } from '../store/auth'
import { useApi } from '../composables/useApi'
import { startDeepResearch, getDeepResearchStatus, getDeepResearchResult, createBundle } from '../api/simulation'
import { getPendingUpload, clearPendingUpload, setPendingUpload } from '../store/pendingUpload'
import { trackEvent } from '../lib/analytics'

const router = useRouter()
const route = useRoute()
const { apiGet, apiPost } = useApi()

const formData = ref({ simulationRequirement: '' })
const files = ref([])
const loading = ref(false)
const error = ref('')
const isDragOver = ref(false)
const fileInput = ref(null)

const enhancing = ref(false)
const showUpgradeModal = ref(false)
const researchLoading = ref(false)
const briefing = ref(null)
const briefingExpanded = ref(false)

const typewriterText = ref('')
const typewriterDone = ref(false)

function normalizeClientPlan(raw) {
  if (raw == null || raw === '') return 'free'
  const s = String(raw).trim().toLowerCase()
  if (s === 'null' || s === 'undefined' || s === 'none') return 'free'
  return s
}

const userPlan = ref('free')
const prefillRestored = ref(false)
const decisionForm = reactive({
  role: '',
  decision: '',
  constraints: '',
  flip_conditions: '',
})
const researchDossier = ref(null)
const researchStatusMessage = ref('Researching...')
const researchElapsed = ref(0)
let researchElapsedTimer = null
let typewriterTimer = null

const fullAnalysisMode = ref(false)
const bundlePlan = ref([])
const bundleLoading = ref(false)
const activeBundleId = ref(null)

onMounted(() => {
  const full = 'Simulate the future'
  let i = 0
  typewriterTimer = setInterval(() => {
    if (i < full.length) {
      typewriterText.value = full.slice(0, ++i)
    } else {
      typewriterDone.value = true
      clearInterval(typewriterTimer)
      typewriterTimer = null
    }
  }, 70)

  apiGet('/billing/status').then(res => {
    if (res?.success) userPlan.value = normalizeClientPlan(res.data?.plan)
  }).catch(() => {
    userPlan.value = 'free'
  })

  if (route.query.prefill) {
    const pending = getPendingUpload()
    if (pending.simulationRequirement) {
      formData.value.simulationRequirement = pending.simulationRequirement
      if (pending.decisionIntake) {
        decisionForm.role = pending.decisionIntake.role || ''
        decisionForm.decision = pending.decisionIntake.decision || ''
        decisionForm.constraints = pending.decisionIntake.constraints || ''
        decisionForm.flip_conditions = pending.decisionIntake.flip_conditions || ''
        prefillRestored.value = true
      }
      clearPendingUpload()
    }
  }
})

onUnmounted(() => {
  if (typewriterTimer) clearInterval(typewriterTimer)
  if (researchElapsedTimer) clearInterval(researchElapsedTimer)
})

const isPaidUser = computed(() => {
  const p = normalizeClientPlan(userPlan.value)
  return ['pro', 'business', 'enterprise', 'payg'].includes(p)
})

const planLimits = computed(() => {
  const p = normalizeClientPlan(userPlan.value)
  if (p === 'business') return { agents: 75, rounds: 30 }
  if (p === 'enterprise') return { agents: 200, rounds: 50 }
  if (p === 'pro' || p === 'payg') return { agents: 50, rounds: 25 }
  return { agents: 25, rounds: 15 }
})

const starterExamples = [
  { icon: '\u{1F3ED}', label: 'US raises tariffs on EU steel by 25%', scenario: 'What happens if the US raises tariffs on EU steel by 25%?' },
  { icon: '\u{1F4CA}', label: 'AI regulation impact on big tech stocks', scenario: 'How will AI regulation affect big tech stock prices over the next 12 months?' },
  { icon: '\u{1F48A}', label: 'Small pharmacy invests in delivery', scenario: 'Should a small independent pharmacy invest in a prescription delivery service?' },
  { icon: '\u{1F3E2}', label: 'Remote work vs commercial real estate', scenario: 'What is the impact of permanent remote work policies on commercial real estate values in major US cities?' },
  { icon: '\u{26A1}', label: 'Energy price cap removal effects', scenario: 'What happens if Ofgem removes the energy price cap in the UK?' },
  { icon: '\u{1F30D}', label: 'EU carbon border tax on manufacturers', scenario: 'How will the EU carbon border adjustment mechanism affect non-EU manufacturers exporting to Europe?' },
]


const canSubmit = computed(() => {
  return formData.value.simulationRequirement.trim() !== ''
})

async function handleEnhancePrompt() {
  const prompt = formData.value.simulationRequirement.trim()
  if (!prompt) return
  enhancing.value = true
  try {
    const docNames = files.value.map(f => f.name)
    const res = await apiPost('/graph/enhance-prompt', {
      prompt,
      document_names: docNames,
    })
    if (res?.success && res.enhanced_prompt) {
      formData.value.simulationRequirement = res.enhanced_prompt
    }
  } catch (e) {
    error.value = 'Prompt enhancement failed'
  } finally {
    enhancing.value = false
  }
}

async function runDeepResearch() {
  if (!isPaidUser.value) return
  const prompt = formData.value.simulationRequirement.trim()
  if (!prompt) return
  researchLoading.value = true
  error.value = ''
  researchElapsed.value = 0
  researchStatusMessage.value = 'Starting deep research...'

  researchElapsedTimer = setInterval(() => { researchElapsed.value++ }, 1000)

  try {
    const startRes = await startDeepResearch(prompt)
    if (!startRes.success) {
      error.value = startRes.error || 'Failed to start deep research'
      return
    }
    const taskId = startRes.data.task_id

    // Poll until complete
    let complete = false
    while (!complete) {
      await new Promise(r => setTimeout(r, 4000))
      const statusRes = await getDeepResearchStatus(taskId)
      if (!statusRes.success) { error.value = 'Lost connection to research task'; return }

      const task = statusRes.data
      researchStatusMessage.value = task.message || 'Research in progress...'

      if (task.status === 'completed') {
        complete = true
      } else if (task.status === 'failed') {
        error.value = task.error || 'Deep research failed'
        return
      }
    }

    const resultRes = await getDeepResearchResult(taskId)
    if (!resultRes.success) { error.value = 'Failed to retrieve research result'; return }

    const dossier = resultRes.data
    researchDossier.value = dossier

    // Create briefing display + file (same pattern as auto-research)
    briefing.value = {
      title: 'Deep Research Dossier',
      content_md: dossier.summary_md || '',
      filename: 'deep_research_dossier.md',
    }
    const blob = new Blob([dossier.summary_md || ''], { type: 'text/markdown' })
    const briefingFile = new File([blob], 'deep_research_dossier.md', { type: 'text/markdown' })
    files.value.push(briefingFile)

  } catch (e) {
    error.value = 'Failed to connect to the server'
  } finally {
    researchLoading.value = false
    if (researchElapsedTimer) { clearInterval(researchElapsedTimer); researchElapsedTimer = null }
  }
}

function removeBriefing() {
  if (briefing.value) {
    const idx = files.value.findIndex(f => f.name === briefing.value.filename)
    if (idx !== -1) files.value.splice(idx, 1)
    briefing.value = null
    briefingExpanded.value = false
  }
}

const triggerFileInput = () => { if (!loading.value) fileInput.value?.click() }
const handleFileSelect = (event) => { addFiles(Array.from(event.target.files)) }
const handleDragOver = () => { if (!loading.value) isDragOver.value = true }
const handleDragLeave = () => { isDragOver.value = false }
const handleDrop = (e) => {
  isDragOver.value = false
  if (loading.value) return
  addFiles(Array.from(e.dataTransfer.files))
}
const addFiles = (newFiles) => {
  const validFiles = newFiles.filter(file => {
    const ext = file.name.split('.').pop().toLowerCase()
    return ['pdf', 'md', 'txt', 'markdown'].includes(ext)
  })
  files.value.push(...validFiles)
}
const removeFile = (index) => { files.value.splice(index, 1) }
const scrollToBottom = () => { window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }) }

watch(() => formData.value.simulationRequirement, () => {
  if (fullAnalysisMode.value) {
    fullAnalysisMode.value = false
    bundlePlan.value = []
  }
})

watch(decisionForm, () => {
  if (prefillRestored.value) prefillRestored.value = false
}, { deep: true })

watch(fullAnalysisMode, async (enabled) => {
  if (!enabled) { bundlePlan.value = []; return }
  const prompt = formData.value.simulationRequirement.trim()
  if (!prompt) { fullAnalysisMode.value = false; return }
  bundleLoading.value = true
  try {
    const res = await createBundle({ title: prompt.slice(0, 100), decision_context: prompt })
    if (!fullAnalysisMode.value) return
    if (res.data) {
      activeBundleId.value = res.data.id
      bundlePlan.value = res.data.suggested_scenarios || []
      trackEvent('bundle_created', { scenario_count: bundlePlan.value.length })
    }
  } catch (e) {
    console.error('Bundle creation failed:', e)
    fullAnalysisMode.value = false
  } finally {
    bundleLoading.value = false
  }
})

const startSimulation = () => {
  if (!canSubmit.value || loading.value) return
  if (!isPaidUser.value) {
    showUpgradeModal.value = true
    return
  }
  const hasDecision = decisionForm.role || decisionForm.decision
  const intake = hasDecision ? { ...decisionForm } : null

  const scenarioText = fullAnalysisMode.value && bundlePlan.value.length > 0
    ? bundlePlan.value[0].scenario
    : formData.value.simulationRequirement

  setPendingUpload(files.value, scenarioText, intake, researchDossier.value)
  router.push({ name: 'Process', params: { projectId: 'new' } })
}
</script>

<style scoped>
.home-container {
  --bg: #0a0a0a;
  --bg-elevated: #111;
  --text-primary: #e0e0e0;
  --text-secondary: #888;
  --accent: #00c853;
  --accent-hover: #00e676;
  --border: #1e1e1e;
  --border-light: #2a2a2a;
  --font-mono: 'JetBrains Mono', monospace;
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  min-height: 100vh;
  background: var(--bg);
  font-family: var(--font-sans);
  color: var(--text-primary);
}

/* ── Animations ── */
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(24px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
@keyframes pulse-border {
  0% { box-shadow: 0 0 0 0 rgba(0, 200, 83, 0.2); }
  70% { box-shadow: 0 0 0 6px rgba(0, 200, 83, 0); }
  100% { box-shadow: 0 0 0 0 rgba(0, 200, 83, 0); }
}
@keyframes pulse-dot {
  0%, 100% { box-shadow: 0 0 0 0 rgba(0, 200, 83, 0.5); }
  50% { box-shadow: 0 0 0 4px rgba(0, 200, 83, 0); }
}

.anim-fade {
  opacity: 0;
  animation: fadeInUp 0.6s ease forwards;
  animation-delay: var(--delay, 0s);
}

/* ── Layout ── */
.main-content {
  max-width: 1400px;
  margin: 0 auto;
  padding: 50px 40px;
}

/* ── Hero ── */
.hero-section {
  display: flex;
  justify-content: space-between;
  margin-bottom: 60px;
  position: relative;
}
.hero-left { flex: 1; padding-right: 60px; }
.tag-row {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 25px;
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}
.accent-tag {
  background: var(--accent);
  color: #000;
  padding: 4px 10px;
  font-weight: 700;
  letter-spacing: 1px;
  font-size: 0.75rem;
}
.version-text { color: #999; font-weight: 500; letter-spacing: 0.5px; }

.main-title {
  font-size: 4.5rem;
  line-height: 1.1;
  font-weight: 700;
  margin: 0 0 36px 0;
  letter-spacing: -0.03em;
  color: #fff;
}
.gradient-text {
  background: linear-gradient(90deg, #fff 0%, #666 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  display: inline;
}
.tw-cursor {
  -webkit-text-fill-color: var(--accent);
  animation: blink 0.7s step-end infinite;
  font-weight: 400;
}

.hero-desc {
  font-size: 1.05rem;
  line-height: 1.8;
  color: var(--text-secondary);
  max-width: 640px;
  margin-bottom: 40px;
  font-weight: 400;
}
.hero-desc p { margin-bottom: 1.2rem; }
.highlight-bold { color: #fff; font-weight: 700; }
.highlight-accent { color: var(--accent); font-weight: 700; }
.highlight-code {
  background: rgba(255, 255, 255, 0.08);
  padding: 2px 6px;
  border-radius: 2px;
  font-family: var(--font-mono);
  font-size: 0.9em;
  color: #fff;
  font-weight: 600;
}
.slogan-text {
  font-size: 1.1rem;
  font-weight: 520;
  color: #fff;
  letter-spacing: 0.5px;
  border-left: 3px solid var(--accent);
  padding-left: 15px;
  margin-top: 16px;
}
.blinking-cursor {
  color: var(--accent);
  animation: blink 1s step-end infinite;
  font-weight: 700;
}
.decoration-square { width: 14px; height: 14px; background: var(--accent); }

.hero-right {
  flex: 0.8;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
}
.logo-container {
  width: 100%;
  display: flex;
  justify-content: flex-end;
  padding-right: 40px;
}
.hero-logo { max-height: 400px; width: auto; object-fit: contain; }
.scroll-down-btn {
  width: 36px;
  height: 36px;
  border: 1px solid var(--border);
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--accent);
  transition: all 0.2s;
}
.scroll-down-btn:hover { border-color: var(--accent); }

/* ── Dashboard ── */
.dashboard-section {
  display: flex;
  gap: 50px;
  border-top: 1px solid var(--border);
  padding-top: 50px;
  align-items: flex-start;
}
.dashboard-section .left-panel,
.dashboard-section .right-panel {
  display: flex;
  flex-direction: column;
}
.left-panel { flex: 0.8; }

.panel-header {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
}
.pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  display: inline-block;
  animation: pulse-dot 2s ease-in-out infinite;
}

.section-title { font-size: 2rem; font-weight: 520; margin: 0 0 12px 0; color: #fff; }
.section-desc { color: var(--text-secondary); margin-bottom: 20px; line-height: 1.6; }

/* ── Metric Cards ── */
.metrics-row { display: flex; gap: 16px; margin-bottom: 20px; }
.metric-card {
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  padding: 20px 24px;
  flex: 1;
}
.metric-icon {
  color: var(--accent);
  margin-bottom: 10px;
  opacity: 0.8;
}
.metric-value {
  font-family: var(--font-mono);
  font-size: 1.8rem;
  font-weight: 600;
  margin-bottom: 4px;
  color: #fff;
}
.metric-label { font-size: 0.82rem; color: var(--text-secondary); }

/* ── Workflow ── */
.steps-container {
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  padding: 24px;
}
.steps-header {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #999;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.workflow-list {
  display: flex;
  flex-direction: column;
  gap: 0;
  border-left: 1px solid var(--border-light);
  margin-left: 8px;
  padding-left: 0;
}
.workflow-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 10px 0 10px 20px;
  position: relative;
}
.workflow-item::before {
  content: '';
  position: absolute;
  left: -4px;
  top: 14px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--border-light);
  border: 1px solid var(--bg-elevated);
}
.step-icon-wrap {
  color: var(--accent);
  opacity: 0.6;
  flex-shrink: 0;
  margin-top: 1px;
}
.step-info { flex: 1; }
.step-title { font-weight: 520; font-size: 0.95rem; margin-bottom: 3px; color: #e0e0e0; }
.step-desc { font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5; }

/* ── Console ── */
.right-panel { flex: 1.2; }
.console-box {
  border: 1px solid var(--border-light);
  padding: 8px;
  box-shadow: inset 0 1px 3px rgba(0,0,0,0.3);
}
.console-section { padding: 20px; }
.console-section.btn-section { padding-top: 0; }
.console-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
}
.console-label {
  display: flex;
  align-items: center;
  gap: 6px;
}
.console-meta { font-family: var(--font-mono); }
.enhance-btn {
  background: transparent;
  border: 1px solid var(--accent);
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 0.7rem;
  padding: 3px 10px;
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  transition: all 0.2s;
}
.enhance-btn:hover:not(:disabled) { background: rgba(0, 200, 83, 0.08); }
.enhance-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.input-wrapper {
  position: relative;
  border: 1px solid var(--border);
  background: var(--bg-elevated);
}
.code-input {
  width: 100%;
  border: none;
  background: transparent;
  padding: 20px;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  min-height: 140px;
  color: #e0e0e0;
}
.model-badge {
  position: absolute;
  bottom: 10px;
  right: 15px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--text-secondary);
}

/* ── Buttons ── */
.start-engine-btn {
  width: 100%;
  background: var(--accent);
  color: #000;
  border: 1px solid var(--accent);
  padding: 18px 20px;
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 1.1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  transition: all 0.3s ease;
  letter-spacing: 1px;
  position: relative;
  overflow: hidden;
}
.start-engine-btn:not(:disabled) { animation: pulse-border 2s infinite; }
.start-engine-btn:hover:not(:disabled) {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
  transform: translateY(-2px);
}
.start-engine-btn:active:not(:disabled) { transform: translateY(0); }
.start-engine-btn:disabled {
  background: #1a1a1a;
  color: #555;
  cursor: not-allowed;
  border-color: #1a1a1a;
}

/* ── Starter Scenario Cards ── */
.starter-scenarios {
  margin: 12px 8px 8px;
}
.starter-header {
  font-size: 11px; text-transform: uppercase; letter-spacing: 1px;
  color: var(--text-muted, #666); margin-bottom: 10px; padding-left: 2px;
}
.starter-cards {
  display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
}
.starter-card {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border, rgba(255,255,255,0.08));
  color: var(--text-secondary, #aaa);
  font-size: 13px; text-align: left; cursor: pointer;
  transition: all 0.2s;
}
.starter-card:hover {
  border-color: var(--accent, #00c853);
  background: rgba(0, 200, 83, 0.06);
  color: var(--text-primary, #fff);
}
.starter-icon { font-size: 16px; flex-shrink: 0; }
.starter-text { line-height: 1.4; }

@media (max-width: 600px) {
  .starter-cards { grid-template-columns: 1fr; }
}

/* ── Example Preview ── */

.auto-research-btn {
  width: 100%;
  padding: 12px 20px;
  background: transparent;
  border: 1px dashed var(--accent);
  color: var(--accent);
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 16px;
}
.auto-research-btn:hover:not(:disabled):not(.disabled) { background: rgba(0, 200, 83, 0.05); }
.auto-research-btn.disabled { border-color: #333; color: #555; cursor: default; }
.auto-research-btn:disabled { opacity: 0.6; cursor: wait; }

.briefing-preview {
  border: 1px solid var(--border);
  margin-bottom: 16px;
  background: var(--bg-elevated);
}
.briefing-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--accent);
}
.briefing-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary); }
.briefing-toggle {
  background: none;
  border: 1px solid var(--border);
  color: var(--accent);
  font-size: 0.7rem;
  font-family: var(--font-mono);
  padding: 2px 8px;
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  transition: all 0.2s;
}
.briefing-toggle:hover { border-color: var(--accent); background: rgba(0, 200, 83, 0.05); }
.briefing-content {
  padding: 12px;
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.6;
  max-height: 120px;
  overflow: hidden;
  white-space: pre-wrap;
  transition: max-height 0.3s ease;
}
.briefing-content.expanded {
  max-height: none;
  overflow-y: auto;
}

/* ── Upload / files ── */
.upload-zone {
  border: 1px dashed var(--border-light);
  height: 160px;
  overflow-y: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s;
  background: var(--bg-elevated);
}
.upload-zone.has-files { align-items: flex-start; }
.upload-zone:hover { background: #1a1a1a; border-color: #444; }
.upload-placeholder { text-align: center; }
.upload-icon {
  width: 40px;
  height: 40px;
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 12px;
  color: var(--text-secondary);
}
.upload-title { font-weight: 500; font-size: 0.9rem; margin-bottom: 4px; color: #ccc; }
.upload-hint { font-size: 0.75rem; color: var(--text-secondary); }
.file-list { width: 100%; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg);
  padding: 8px 12px;
  border: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: #ccc;
}
.file-name { flex: 1; }
.remove-btn { background: none; border: none; cursor: pointer; font-size: 1.2rem; color: #666; }
.remove-btn:hover { color: #c62828; }

.console-divider {
  display: flex;
  align-items: center;
  margin: 10px 0;
}
.console-divider::before,
.console-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}
.console-divider span {
  padding: 0 15px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--text-secondary);
  letter-spacing: 1px;
}
.inner-divider { margin: 0 0 12px 0; }

/* Upgrade Modal */
.modal-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0, 0, 0, 0.7); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.upgrade-modal {
  background: var(--bg-elevated, #1a1a1a); border: 1px solid var(--border, #333);
  border-radius: 16px; padding: 40px; max-width: 420px; width: 90%;
  text-align: center; position: relative;
}
.modal-close {
  position: absolute; top: 12px; right: 16px;
  background: none; border: none; color: var(--text-secondary); font-size: 24px; cursor: pointer;
}
.modal-close:hover { color: #fff; }
.modal-icon { margin-bottom: 16px; color: var(--accent, #00b894); }
.modal-title { font-size: 1.2rem; font-weight: 700; margin-bottom: 10px; color: #fff; }
.modal-desc { font-size: 0.9rem; color: var(--text-secondary); line-height: 1.6; margin-bottom: 24px; }
.modal-actions { display: flex; flex-direction: column; gap: 10px; }
.modal-btn {
  padding: 14px 20px; border-radius: 8px; font-weight: 600; font-size: 0.95rem;
  cursor: pointer; border: none; transition: all 0.2s;
}
.modal-btn.primary { background: var(--accent, #00b894); color: #000; }
.modal-btn.primary:hover { filter: brightness(1.1); }
.modal-btn.secondary { background: transparent; border: 1px solid var(--border, #333); color: var(--text-secondary); }
.modal-btn.secondary:hover { border-color: var(--accent); color: #fff; }

/* Decision Context Form */
.decision-context-form { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.decision-field { display: flex; flex-direction: column; gap: 2px; }
.decision-label { font-size: 11px; color: var(--text-secondary); font-family: var(--font-mono); text-transform: uppercase; letter-spacing: 0.5px; }
.decision-input { background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; color: var(--text-primary); font-size: 13px; font-family: var(--font-sans); transition: border-color 0.2s; }
.prefill-restored-hint { font-size: 11px; color: var(--accent, #00e0ff); font-family: var(--font-mono); opacity: 0.75; margin-top: 4px; }
.decision-input:focus { outline: none; border-color: var(--accent); }
.decision-input::placeholder { color: #555; }

/* Research loading */
.research-loading-content { display: inline-flex; align-items: center; gap: 8px; }
.pulse-indicator { width: 8px; height: 8px; background: var(--accent); border-radius: 50%; animation: pulse-glow 1.5s ease-in-out infinite; }
@keyframes pulse-glow { 0%, 100% { opacity: 1; box-shadow: 0 0 4px var(--accent); } 50% { opacity: 0.4; box-shadow: 0 0 12px var(--accent); } }

/* Error display */
.research-error { margin-top: 8px; padding: 8px 12px; background: rgba(220, 38, 38, 0.1); border: 1px solid rgba(220, 38, 38, 0.3); border-radius: 6px; color: #f87171; font-size: 13px; }

/* Bundle Toggle & Preview */
.bundle-toggle-section { padding: 12px 16px !important; }
.bundle-toggle {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px; cursor: pointer;
}
.bundle-toggle input[type="checkbox"] {
  width: 16px; height: 16px; accent-color: var(--accent);
}
.bundle-toggle-label { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.bundle-toggle-hint { font-size: 11px; color: var(--text-secondary); width: 100%; margin-left: 24px; }

.bundle-preview { padding: 12px 16px !important; }
.bundle-preview-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;
}
.bundle-preview-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--accent); font-weight: 600; }
.bundle-preview-count { font-size: 11px; color: var(--text-secondary); font-family: var(--font-mono); }
.bundle-preview-list { display: flex; flex-direction: column; gap: 6px; }
.bundle-preview-item {
  display: flex; align-items: flex-start; gap: 10px; padding: 8px 10px;
  border-radius: 5px; background: rgba(255,255,255,0.02); border: 1px solid var(--border);
}
.bundle-preview-idx {
  font-family: var(--font-mono); font-size: 11px; color: #555;
  min-width: 18px; text-align: center; padding-top: 1px;
}
.bundle-preview-title { font-size: 12px; font-weight: 500; color: var(--text-primary); }
.bundle-preview-change { font-size: 11px; color: var(--text-secondary); }
.bundle-preview-info { display: flex; flex-direction: column; gap: 2px; }
.bundle-loading {
  display: flex; align-items: center; gap: 8px; padding: 12px 16px !important;
  font-size: 12px; color: var(--text-secondary);
}
.bundle-spinner {
  width: 14px; height: 14px; border: 2px solid var(--border);
  border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite;
}

@media (max-width: 1024px) {
  .dashboard-section { flex-direction: column; }
  .hero-section { flex-direction: column; }
  .hero-left { padding-right: 0; margin-bottom: 40px; }
  .hero-logo { max-height: 160px; margin-bottom: 20px; }
  .main-title { font-size: 2.8rem; }
  .example-row { flex-direction: column; }
}
</style>
