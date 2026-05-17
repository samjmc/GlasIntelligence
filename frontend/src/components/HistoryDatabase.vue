<template>
  <div 
    class="history-database"
    :class="{ 'no-projects': projects.length === 0 && !loading }"
    ref="historyContainer"
  >
    <!-- Background decoration: tech grid (shown only when projects exist) -->
    <div v-if="projects.length > 0 || loading" class="tech-grid-bg">
      <div class="grid-pattern"></div>
      <div class="gradient-overlay"></div>
    </div>

    <!-- Title area -->
    <div class="section-header">
      <div class="section-line"></div>
      <span class="section-title">Simulation History</span>
      <div class="section-line"></div>
    </div>
    <div v-if="projects.length > 1 && isExpanded" class="compare-toolbar">
      <label class="select-mode-toggle">
        <input type="checkbox" v-model="selectMode" />
        <span>Select to Compare</span>
      </label>
      <button
        v-if="selectedIds.size >= 2"
        class="compare-btn"
        @click="goToCompare"
      >Compare {{ selectedIds.size }} Scenarios</button>
    </div>

    <!-- Cards container (shown only when projects exist) -->
    <div v-if="projects.length > 0" class="cards-container" :class="{ expanded: isExpanded }" :style="containerStyle">
      <div 
        v-for="(project, index) in projects" 
        :key="project.simulation_id"
        class="project-card"
        :class="{ expanded: isExpanded, hovering: hoveringCard === index }"
        :style="getCardStyle(index)"
        @mouseenter="hoveringCard = index"
        @mouseleave="hoveringCard = null"
        @click="selectMode ? toggleSelect(project) : navigateToProject(project)"
      >
        <div v-if="selectMode" class="card-select-check" :class="{ checked: selectedIds.has(project.report_id), disabled: !project.report_id }">
          <svg v-if="selectedIds.has(project.report_id)" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#00c853" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
        </div>
        <!-- Card header: simulation_id and feature availability -->
        <div class="card-header">
          <span class="card-id">{{ formatSimulationId(project.simulation_id) }}</span>
          <div class="card-status-icons">
            <span 
              class="status-icon" 
              :class="{ available: project.project_id, unavailable: !project.project_id }"
              title="Knowledge Graph"
            >◇</span>
            <span 
              class="status-icon available" 
              title="Environment Setup"
            >◈</span>
            <span 
              class="status-icon" 
              :class="{ available: project.report_id, unavailable: !project.report_id }"
              title="Report"
            >◆</span>
          </div>
        </div>

        <!-- Files list area -->
        <div class="card-files-wrapper">
          <!-- Corner decoration - viewfinder style -->
          <div class="corner-mark top-left-only"></div>
          
          <!-- Files list -->
          <div class="files-list" v-if="project.files && project.files.length > 0">
            <div 
              v-for="(file, fileIndex) in project.files.slice(0, 3)" 
              :key="fileIndex"
              class="file-item"
            >
              <span class="file-tag" :class="getFileType(file.filename)">{{ getFileTypeLabel(file.filename) }}</span>
              <span class="file-name">{{ truncateFilename(file.filename, 20) }}</span>
            </div>
            <!-- If more files exist, show hint -->
            <div v-if="project.files.length > 3" class="files-more">
              +{{ project.files.length - 3 }} files
            </div>
          </div>
          <!-- Placeholder when no files -->
          <div class="files-empty" v-else>
            <span class="empty-file-icon">◇</span>
            <span class="empty-file-text">No files</span>
          </div>
        </div>

        <!-- Card title (first 20 chars of simulation requirement) -->
        <h3 class="card-title">{{ getSimulationTitle(project.simulation_requirement) }}</h3>

        <!-- Card description (full simulation requirement) -->
        <p class="card-desc">{{ truncateText(project.simulation_requirement, 55) }}</p>

        <!-- Card footer -->
        <div class="card-footer">
          <div class="card-datetime">
            <span class="card-date">{{ formatDate(project.created_at) }}</span>
            <span class="card-time">{{ formatTime(project.created_at) }}</span>
          </div>
          <span class="card-progress" :class="getProgressClass(project)">
            <span class="status-dot">●</span> {{ formatRounds(project) }}
          </span>
        </div>
        
        <!-- Bottom decoration line (expand on hover) -->
        <div class="card-bottom-line"></div>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="loading-state">
      <span class="loading-spinner"></span>
      <span class="loading-text">Loading...</span>
    </div>

    <div v-if="loadError && !loading" class="load-error">{{ loadError }}</div>

    <div v-if="!loading && !loadError && projects.length === 0" class="history-empty">
      <p class="history-empty-title">No simulations in your history yet</p>
      <p class="history-empty-hint">Run a simulation from the scenario box above — completed runs will appear here.</p>
    </div>

    <!-- History replay detail modal -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="selectedProject" class="modal-overlay" @click.self="closeModal">
          <div class="modal-content">
            <!-- Modal header -->
            <div class="modal-header">
              <div class="modal-title-section">
                <span class="modal-id">{{ formatSimulationId(selectedProject.simulation_id) }}</span>
                <span class="modal-progress" :class="getProgressClass(selectedProject)">
                  <span class="status-dot">●</span> {{ formatRounds(selectedProject) }}
                </span>
                <span class="modal-create-time">{{ formatDate(selectedProject.created_at) }} {{ formatTime(selectedProject.created_at) }}</span>
              </div>
              <button class="modal-close" @click="closeModal">×</button>
            </div>

            <!-- Modal body -->
            <div class="modal-body">
              <!-- Simulation requirement -->
              <div class="modal-section">
                <div class="modal-label">Scenario</div>
                <div class="modal-requirement">{{ selectedProject.simulation_requirement || 'None' }}</div>
              </div>

              <!-- Files list -->
              <div class="modal-section">
                <div class="modal-label">Files</div>
                <div class="modal-files" v-if="selectedProject.files && selectedProject.files.length > 0">
                  <div v-for="(file, index) in selectedProject.files" :key="index" class="modal-file-item">
                    <span class="file-tag" :class="getFileType(file.filename)">{{ getFileTypeLabel(file.filename) }}</span>
                    <span class="modal-file-name">{{ file.filename }}</span>
                  </div>
                </div>
                <div class="modal-empty" v-else>No files</div>
              </div>
            </div>

            <!-- Replay simulation divider -->
            <div class="modal-divider">
              <span class="divider-line"></span>
              <span class="divider-text">Replay Simulation</span>
              <span class="divider-line"></span>
            </div>

            <!-- Navigation buttons -->
            <div class="modal-actions">
              <button 
                class="modal-btn btn-project" 
                @click="goToProject"
                :disabled="!selectedProject.project_id"
              >
                <span class="btn-step">Step1</span>
                <span class="btn-icon">◇</span>
                <span class="btn-text">Knowledge Graph</span>
              </button>
              <button 
                class="modal-btn btn-simulation" 
                @click="goToSimulation"
              >
                <span class="btn-step">Step2</span>
                <span class="btn-icon">◈</span>
                <span class="btn-text">Environment Setup</span>
              </button>
              <button 
                class="modal-btn btn-report" 
                @click="goToReport"
                :disabled="!selectedProject.report_id"
              >
                <span class="btn-step">Step4</span>
                <span class="btn-icon">◆</span>
                <span class="btn-text">Report</span>
              </button>
            </div>
            <!-- Re-run with the same scenario -->
            <div class="modal-rerun">
              <button class="modal-btn btn-rerun" @click="rerunScenario">
                <span class="btn-icon">↻</span>
                <span class="btn-text">Re-run This Scenario</span>
              </button>
            </div>
            <!-- Non-replayable hint -->
            <div class="modal-playback-hint">
              <span class="hint-text">Steps 3 and 5 require an active simulation and cannot be replayed</span>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, onActivated, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { getSimulationHistory } from '../api/simulation'
import { setPendingUpload } from '../store/pendingUpload'

const router = useRouter()
const route = useRoute()

// State
const projects = ref([])
const loading = ref(true)
const loadError = ref('')
const isExpanded = ref(false)
const isContainerVisible = ref(false)
const hoveringCard = ref(null)
const historyContainer = ref(null)
const selectedProject = ref(null)
const selectMode = ref(false)
const selectedIds = ref(new Set())
let observer = null
let isAnimating = false  // Animation lock to prevent flicker
let expandDebounceTimer = null  // Debounce timer
let pendingState = null  // Pending target state

// Card layout config - wider ratio
const CARDS_PER_ROW = 4
const CARD_WIDTH = 280  
const CARD_HEIGHT = 280 
const CARD_GAP = 24

// Dynamically compute container height style
const containerStyle = computed(() => {
  if (!isExpanded.value) {
    // Collapsed: fixed height
    return { minHeight: '420px' }
  }
  
  // Expanded: compute height by card count
  const total = projects.value.length
  if (total === 0) {
    return { minHeight: '280px' }
  }
  
  const rows = Math.ceil(total / CARDS_PER_ROW)
  // Compute actual height: rows * card height + (rows-1) * gap + bottom padding
  const expandedHeight = rows * CARD_HEIGHT + (rows - 1) * CARD_GAP + 10
  
  return { minHeight: `${expandedHeight}px` }
})

// Get card style
const getCardStyle = (index) => {
  const total = projects.value.length
  
  if (isExpanded.value) {
    // Expanded: grid layout
    const transition = 'transform 700ms cubic-bezier(0.23, 1, 0.32, 1), opacity 700ms cubic-bezier(0.23, 1, 0.32, 1), box-shadow 0.3s ease, border-color 0.3s ease'

    const col = index % CARDS_PER_ROW
    const row = Math.floor(index / CARDS_PER_ROW)
    
    // Compute cards per row for centering
    const currentRowStart = row * CARDS_PER_ROW
    const currentRowCards = Math.min(CARDS_PER_ROW, total - currentRowStart)
    
    const rowWidth = currentRowCards * CARD_WIDTH + (currentRowCards - 1) * CARD_GAP
    
    const startX = -(rowWidth / 2) + (CARD_WIDTH / 2)
    const colInRow = index % CARDS_PER_ROW
    const x = startX + colInRow * (CARD_WIDTH + CARD_GAP)
    
    // Expand downward, add spacing from title
    const y = 20 + row * (CARD_HEIGHT + CARD_GAP)

    return {
      transform: `translate(${x}px, ${y}px) rotate(0deg) scale(1)`,
      zIndex: 100 + index,
      opacity: 1,
      transition: transition
    }
  } else {
    // Collapsed: fan stack
    const transition = 'transform 700ms cubic-bezier(0.23, 1, 0.32, 1), opacity 700ms cubic-bezier(0.23, 1, 0.32, 1), box-shadow 0.3s ease, border-color 0.3s ease'

    const centerIndex = (total - 1) / 2
    const offset = index - centerIndex
    
    const x = offset * 35
    // Adjust start position, near title with spacing
    const y = 25 + Math.abs(offset) * 8
    const r = offset * 3
    const s = 0.95 - Math.abs(offset) * 0.05
    
    return {
      transform: `translate(${x}px, ${y}px) rotate(${r}deg) scale(${s})`,
      zIndex: 10 + index,
      opacity: 1,
      transition: transition
    }
  }
}

// Get style class by round progress
const getProgressClass = (simulation) => {
  const current = simulation.current_round || 0
  const total = simulation.total_rounds || 0
  
  if (total === 0 || current === 0) {
    // Not started
    return 'not-started'
  } else if (current >= total) {
    // Completed
    return 'completed'
  } else {
    // In progress
    return 'in-progress'
  }
}

// Format date (date part only)
const formatDate = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    return date.toISOString().slice(0, 10)
  } catch {
    return dateStr?.slice(0, 10) || ''
  }
}

// Format time (hour:minute)
const formatTime = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    const hours = date.getHours().toString().padStart(2, '0')
    const minutes = date.getMinutes().toString().padStart(2, '0')
    return `${hours}:${minutes}`
  } catch {
    return ''
  }
}

// Truncate text
const truncateText = (text, maxLength) => {
  if (!text) return ''
  return text.length > maxLength ? text.slice(0, maxLength) + '...' : text
}

// Generate title from simulation requirement (first 20 chars)
const getSimulationTitle = (requirement) => {
  if (!requirement) return 'Unnamed Simulation'
  const title = requirement.slice(0, 20)
  return requirement.length > 20 ? title + '...' : title
}

// Format simulation_id display (first 6 chars)
const formatSimulationId = (simulationId) => {
  if (!simulationId) return 'SIM_UNKNOWN'
  const prefix = simulationId.replace('sim_', '').slice(0, 6)
  return `SIM_${prefix.toUpperCase()}`
}

// Format rounds display (current/total)
const formatRounds = (simulation) => {
  const current = simulation.current_round || 0
  const total = simulation.total_rounds || 0
  if (total === 0) return 'Not Started'
  return `${current}/${total} rounds`
}

// Get file type (for styling)
const getFileType = (filename) => {
  if (!filename) return 'other'
  const ext = filename.split('.').pop()?.toLowerCase()
  const typeMap = {
    'pdf': 'pdf',
    'doc': 'doc', 'docx': 'doc',
    'xls': 'xls', 'xlsx': 'xls', 'csv': 'xls',
    'ppt': 'ppt', 'pptx': 'ppt',
    'txt': 'txt', 'md': 'txt', 'json': 'code',
    'jpg': 'img', 'jpeg': 'img', 'png': 'img', 'gif': 'img',
    'zip': 'zip', 'rar': 'zip', '7z': 'zip'
  }
  return typeMap[ext] || 'other'
}

// Get file type label text
const getFileTypeLabel = (filename) => {
  if (!filename) return 'FILE'
  const ext = filename.split('.').pop()?.toUpperCase()
  return ext || 'FILE'
}

// Truncate filename (keep extension)
const truncateFilename = (filename, maxLength) => {
  if (!filename) return 'Unknown file'
  if (filename.length <= maxLength) return filename
  
  const ext = filename.includes('.') ? '.' + filename.split('.').pop() : ''
  const nameWithoutExt = filename.slice(0, filename.length - ext.length)
  const truncatedName = nameWithoutExt.slice(0, maxLength - ext.length - 3) + '...'
  return truncatedName + ext
}

// Open project detail modal
const navigateToProject = (simulation) => {
  selectedProject.value = simulation
}

// Close modal
const closeModal = () => {
  selectedProject.value = null
}

// Navigate to graph build page (Project)
const goToProject = () => {
  if (selectedProject.value?.project_id) {
    router.push({
      name: 'Process',
      params: { projectId: selectedProject.value.project_id }
    })
    closeModal()
  }
}

// Navigate to environment setup page (Simulation)
const goToSimulation = () => {
  if (selectedProject.value?.simulation_id) {
    router.push({
      name: 'Simulation',
      params: { simulationId: selectedProject.value.simulation_id }
    })
    closeModal()
  }
}

// Navigate to report page (Report)
const goToReport = () => {
  if (selectedProject.value?.report_id) {
    router.push({
      name: 'Report',
      params: { reportId: selectedProject.value.report_id }
    })
    closeModal()
  }
}

const toggleSelect = (project) => {
  if (!project.report_id) return
  const id = project.report_id
  const next = new Set(selectedIds.value)
  if (next.has(id)) {
    next.delete(id)
  } else if (next.size < 4) {
    next.add(id)
  }
  selectedIds.value = next
}

const goToCompare = () => {
  const ids = [...selectedIds.value].join(',')
  router.push({ name: 'Compare', query: { ids } })
}

const rerunScenario = () => {
  if (selectedProject.value?.simulation_requirement) {
    setPendingUpload(
      [],
      selectedProject.value.simulation_requirement,
      selectedProject.value.decision_intake || null,
      null
    )
    closeModal()
    router.push({ name: 'Home', query: { prefill: '1' } })
  }
}

// Load history projects
const loadHistory = async () => {
  try {
    loading.value = true
    loadError.value = ''
    const response = await getSimulationHistory(20)
    if (response.success) {
      projects.value = response.data || []
    }
  } catch (error) {
    console.error('Failed to load history:', error)
    projects.value = []
    loadError.value = 'Failed to load simulation history'
  } finally {
    loading.value = false
  }
}

// When projects first load while the section is already in view, trigger expansion.
// This covers the race where the observer fired before the API response arrived.
watch(
  () => projects.value.length > 0,
  (hasProjects) => {
    if (hasProjects && isContainerVisible.value && !isExpanded.value) {
      setTimeout(() => { isExpanded.value = true }, 50)
    }
  },
  { once: true }
)

// Initialize IntersectionObserver
const initObserver = () => {
  if (observer) {
    observer.disconnect()
  }
  
  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        const shouldExpand = entry.isIntersecting
        isContainerVisible.value = shouldExpand

        // Update pending target state (always record latest regardless of animation)
        pendingState = shouldExpand

        // Don't expand/collapse before projects are loaded — the watch below
        // will fire the expansion once projects arrive.
        if (projects.value.length === 0) return
        
        // Clear previous debounce timer (new scroll intent overrides old)
        if (expandDebounceTimer) {
          clearTimeout(expandDebounceTimer)
          expandDebounceTimer = null
        }
        
        // If animating, only record state, process after animation ends
        if (isAnimating) return
        
        // If target state same as current, no action needed
        if (shouldExpand === isExpanded.value) {
          pendingState = null
          return
        }
        
        // Use debounce for state switch to prevent flicker
        // Shorter delay when expanding (50ms), longer when collapsing (200ms) for stability
        const delay = shouldExpand ? 50 : 200
        
        expandDebounceTimer = setTimeout(() => {
          // Check if animating
          if (isAnimating) return
          
          // Check if pending state still needs execution (may be overridden by scroll)
          if (pendingState === null || pendingState === isExpanded.value) return
          
          // Set animation lock
          isAnimating = true
          isExpanded.value = pendingState
          pendingState = null
          
          // Unlock after animation, check for pending state changes
          setTimeout(() => {
            isAnimating = false
            
            // After animation, check for new pending state
            if (pendingState !== null && pendingState !== isExpanded.value) {
              // Delay slightly before executing to avoid rapid switching
              expandDebounceTimer = setTimeout(() => {
                if (pendingState !== null && pendingState !== isExpanded.value) {
                  isAnimating = true
                  isExpanded.value = pendingState
                  pendingState = null
                  setTimeout(() => {
                    isAnimating = false
                  }, 750)
                }
              }, 100)
            }
          }, 750)
        }, delay)
      })
    },
    {
      // Use multiple thresholds for smoother detection
      threshold: [0.4, 0.6, 0.8],
      // Adjust rootMargin, viewport bottom shrinks up, need more scroll to trigger expand
      rootMargin: '0px 0px -150px 0px'
    }
  )
  
  // Start observing
  if (historyContainer.value) {
    observer.observe(historyContainer.value)
  }
}

// Watch route changes, reload data when returning home
watch(() => route.path, (newPath) => {
  if (newPath === '/') {
    loadHistory()
  }
})

onMounted(async () => {
  // Ensure DOM is ready before loading data
  await nextTick()
  await loadHistory()
  
  // Initialize observer after DOM render
  setTimeout(() => {
    initObserver()
  }, 100)
})

// If using keep-alive, reload data when component activated
onActivated(() => {
  selectMode.value = false
  selectedIds.value = new Set()
  loadHistory()
})

onUnmounted(() => {
  // Cleanup Intersection Observer
  if (observer) {
    observer.disconnect()
    observer = null
  }
  // Cleanup debounce timer
  if (expandDebounceTimer) {
    clearTimeout(expandDebounceTimer)
    expandDebounceTimer = null
  }
})
</script>

<style scoped src="./HistoryDatabase.scoped.css"></style>
