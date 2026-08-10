<template>
  <div class="simulation-panel">
    <!-- Top Control Bar -->
    <div class="control-bar">
      <div class="status-group">
        <!-- Twitter Platform Progress -->
        <div class="platform-status twitter" :class="{ active: runStatus.twitter_running, completed: runStatus.twitter_completed }">
          <div class="platform-header">
            <svg class="platform-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
            </svg>
            <span class="platform-name">Info Plaza</span>
            <span v-if="runStatus.twitter_completed" class="status-badge">
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </span>
          </div>
          <div class="platform-stats">
            <span class="stat">
              <span class="stat-label">ROUND</span>
              <span class="stat-value mono">{{ runStatus.twitter_current_round || 0 }}<span class="stat-total">/{{ runStatus.total_rounds || maxRounds || '-' }}</span></span>
            </span>
            <span class="stat">
              <span class="stat-label">{{ elapsedTimeStatLabel }}</span>
              <span class="stat-value mono">{{ twitterElapsedTime }}</span>
            </span>
            <span class="stat">
              <span class="stat-label">ACTS</span>
              <span class="stat-value mono">{{ runStatus.twitter_actions_count || 0 }}</span>
            </span>
          </div>
          <div class="actions-tooltip">
            <div class="tooltip-title">Available Actions</div>
            <div class="tooltip-actions">
              <span class="tooltip-action">POST</span>
              <span class="tooltip-action">LIKE</span>
              <span class="tooltip-action">REPOST</span>
              <span class="tooltip-action">QUOTE</span>
              <span class="tooltip-action">FOLLOW</span>
              <span class="tooltip-action">IDLE</span>
              <span class="tooltip-action tool-action">TOOLS</span>
            </div>
          </div>
        </div>
        
        <!-- Reddit Platform Progress -->
        <div class="platform-status reddit" :class="{ active: runStatus.reddit_running, completed: runStatus.reddit_completed }">
          <div class="platform-header">
            <svg class="platform-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>
            </svg>
            <span class="platform-name">Topic Community</span>
            <span v-if="runStatus.reddit_completed" class="status-badge">
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </span>
          </div>
          <div class="platform-stats">
            <span class="stat">
              <span class="stat-label">ROUND</span>
              <span class="stat-value mono">{{ runStatus.reddit_current_round || 0 }}<span class="stat-total">/{{ runStatus.total_rounds || maxRounds || '-' }}</span></span>
            </span>
            <span class="stat">
              <span class="stat-label">{{ elapsedTimeStatLabel }}</span>
              <span class="stat-value mono">{{ redditElapsedTime }}</span>
            </span>
            <span class="stat">
              <span class="stat-label">ACTS</span>
              <span class="stat-value mono">{{ runStatus.reddit_actions_count || 0 }}</span>
            </span>
          </div>
          <div class="actions-tooltip">
            <div class="tooltip-title">Available Actions</div>
            <div class="tooltip-actions">
              <span class="tooltip-action">POST</span>
              <span class="tooltip-action">COMMENT</span>
              <span class="tooltip-action">LIKE</span>
              <span class="tooltip-action">DISLIKE</span>
              <span class="tooltip-action">SEARCH</span>
              <span class="tooltip-action">TREND</span>
              <span class="tooltip-action">FOLLOW</span>
              <span class="tooltip-action">MUTE</span>
              <span class="tooltip-action">REFRESH</span>
              <span class="tooltip-action">IDLE</span>
              <span class="tooltip-action tool-action">TOOLS</span>
            </div>
          </div>
        </div>
      </div>

      <div class="action-controls">
        <label v-if="phase === 0" class="graph-memory-opt">
          <input
            v-model="enableGraphMemoryUpdate"
            type="checkbox"
            :disabled="isStarting"
          />
          <span class="graph-memory-text">Live graph memory (Zep — higher usage)</span>
        </label>
        <button
          data-test="simulation-complete"
          class="action-btn primary"
          :disabled="phase !== 2 || isGeneratingReport"
          @click="handleNextStep"
        >
          <span v-if="isGeneratingReport" class="loading-spinner-small"></span>
          {{ isGeneratingReport ? 'Starting...' : 'Generate Report' }}
          <span v-if="!isGeneratingReport" class="arrow-icon">→</span>
        </button>
      </div>
    </div>

    <!-- Main Content: Dual Timeline -->
    <div class="main-content-area" ref="scrollContainer">
      <!-- Timeline Header -->
      <div class="timeline-header" v-if="allActions.length > 0">
        <div class="timeline-stats">
          <span class="total-count">TOTAL EVENTS: <span class="mono">{{ allActions.length }}</span></span>
          <span class="platform-breakdown">
            <span class="breakdown-item twitter">
              <svg class="mini-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>
              <span class="mono">{{ twitterActionsCount }}</span>
            </span>
            <span class="breakdown-divider">/</span>
            <span class="breakdown-item reddit">
              <svg class="mini-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
              <span class="mono">{{ redditActionsCount }}</span>
            </span>
          </span>
        </div>
      </div>
      
      <!-- Timeline Feed -->
      <div class="timeline-feed">
        <div class="timeline-axis"></div>
        
        <TransitionGroup name="timeline-item">
          <div 
            v-for="action in chronologicalActions" 
            :key="action._uniqueId || action.id || `${action.timestamp}-${action.agent_id}`" 
            class="timeline-item"
            :class="action.platform"
          >
            <div class="timeline-marker">
              <div class="marker-dot"></div>
            </div>
            
            <div class="timeline-card">
              <div class="card-header">
                <div class="agent-info">
                  <div class="avatar-placeholder">{{ (action.agent_name || 'A')[0] }}</div>
                  <span class="agent-name">{{ action.agent_name }}</span>
                </div>
                
                <div class="header-meta">
                  <div class="platform-indicator">
                    <svg v-if="action.platform === 'twitter'" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>
                    <svg v-else viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
                  </div>
                  <div class="action-badge" :class="getActionTypeClass(action.action_type)">
                    {{ getActionTypeLabel(action.action_type) }}
                  </div>
                </div>
              </div>
              
              <div class="card-body">
                <!-- CREATE_POST -->
                <div v-if="action.action_type === 'CREATE_POST' && action.action_args?.content" class="content-text main-text">
                  {{ action.action_args.content }}
                </div>

                <!-- QUOTE_POST -->
                <template v-if="action.action_type === 'QUOTE_POST'">
                  <div v-if="action.action_args?.quote_content" class="content-text">
                    {{ action.action_args.quote_content }}
                  </div>
                  <div v-if="action.action_args?.original_content" class="quoted-block">
                    <div class="quote-header">
                      <svg class="icon-small" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
                      <span class="quote-label">@{{ action.action_args.original_author_name || 'User' }}</span>
                    </div>
                    <div class="quote-text">
                      {{ truncateContent(action.action_args.original_content, 150) }}
                    </div>
                  </div>
                </template>

                <!-- REPOST -->
                <template v-if="action.action_type === 'REPOST'">
                  <div class="repost-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="17 1 21 5 17 9"></polyline><path d="M3 11V9a4 4 0 0 1 4-4h14"></path><polyline points="7 23 3 19 7 15"></polyline><path d="M21 13v2a4 4 0 0 1-4 4H3"></path></svg>
                    <span class="repost-label">Reposted from @{{ action.action_args?.original_author_name || 'User' }}</span>
                  </div>
                  <div v-if="action.action_args?.original_content" class="repost-content">
                    {{ truncateContent(action.action_args.original_content, 200) }}
                  </div>
                </template>

                <!-- LIKE_POST -->
                <template v-if="action.action_type === 'LIKE_POST'">
                  <div class="like-info">
                    <svg class="icon-small filled" viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
                    <span class="like-label">Liked @{{ action.action_args?.post_author_name || 'User' }}'s post</span>
                  </div>
                  <div v-if="action.action_args?.post_content" class="liked-content">
                    "{{ truncateContent(action.action_args.post_content, 120) }}"
                  </div>
                </template>

                <!-- CREATE_COMMENT -->
                <template v-if="action.action_type === 'CREATE_COMMENT'">
                  <div v-if="action.action_args?.content" class="content-text">
                    {{ action.action_args.content }}
                  </div>
                  <div v-if="action.action_args?.post_id" class="comment-context">
                    <svg class="icon-small" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
                    <span>Reply to post #{{ action.action_args.post_id }}</span>
                  </div>
                </template>

                <!-- SEARCH_POSTS -->
                <template v-if="action.action_type === 'SEARCH_POSTS'">
                  <div class="search-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                    <span class="search-label">Search Query:</span>
                    <span class="search-query">"{{ action.action_args?.query || '' }}"</span>
                  </div>
                </template>

                <!-- FOLLOW -->
                <template v-if="action.action_type === 'FOLLOW'">
                  <div class="follow-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="8.5" cy="7" r="4"></circle><line x1="20" y1="8" x2="20" y2="14"></line><line x1="23" y1="11" x2="17" y2="11"></line></svg>
                    <span class="follow-label">Followed @{{ action.action_args?.target_user || action.action_args?.user_id || 'User' }}</span>
                  </div>
                </template>

                <!-- UPVOTE / DOWNVOTE -->
                <template v-if="action.action_type === 'UPVOTE_POST' || action.action_type === 'DOWNVOTE_POST'">
                  <div class="vote-info">
                    <svg v-if="action.action_type === 'UPVOTE_POST'" class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg>
                    <svg v-else class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
                    <span class="vote-label">{{ action.action_type === 'UPVOTE_POST' ? 'Upvoted' : 'Downvoted' }} Post</span>
                  </div>
                  <div v-if="action.action_args?.post_content" class="voted-content">
                    "{{ truncateContent(action.action_args.post_content, 120) }}"
                  </div>
                </template>

                <!-- DO_NOTHING -->
                <template v-if="action.action_type === 'DO_NOTHING'">
                  <div class="idle-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                    <span class="idle-label">Action Skipped</span>
                  </div>
                </template>

                <!-- TOOL USE (action_type starts with TOOL_) -->
                <template v-if="action.action_type?.startsWith('TOOL_')">
                  <div class="tool-action-card">
                    <div class="tool-header">
                      <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path></svg>
                      <span class="tool-name">{{ action.action_args?.tool_name || 'Tool' }}</span>
                    </div>
                    <div v-if="getToolInput(action)" class="tool-input">
                      <span class="tool-input-label">Input:</span>
                      <span class="tool-input-value">{{ getToolInput(action) }}</span>
                    </div>
                    <div v-if="action.action_args?.tool_result" class="tool-result">
                      <span class="tool-result-label">Result:</span>
                      <span class="tool-result-value">{{ truncateContent(action.action_args.tool_result, 200) }}</span>
                    </div>
                  </div>
                </template>

                <!-- STATE CHANGE (action_type starts with STATE_) -->
                <template v-if="action.action_type?.startsWith('STATE_')">
                  <div class="state-change-card">
                    <div class="state-header">
                      <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
                      <span class="state-label">{{ getStateChangeLabel(action) }}</span>
                    </div>
                    <div class="state-detail">
                      <span class="state-target">
                        <svg class="icon-tiny" viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                        {{ action.action_args?.target_name || 'Unknown' }}
                      </span>
                      <span v-if="action.action_args?.caused_by_tool" class="state-cause">via {{ action.action_args.caused_by_tool }}</span>
                    </div>
                    <div v-if="getStateChangeDelta(action)" class="state-delta">
                      {{ getStateChangeDelta(action) }}
                    </div>
                  </div>
                </template>

                <!-- Fallback for unknown action types -->
                <div v-if="!isKnownActionType(action.action_type) && action.action_args?.content" class="content-text">
                  {{ action.action_args.content }}
                </div>
              </div>

              <div class="card-footer">
                <span class="time-tag">
                  <template v-if="action.time_label">{{ action.time_label }}</template>
                  <template v-else>R{{ action.round_num }} • {{ formatActionTime(action.timestamp) }}</template>
                </span>
                <!-- Platform tag removed as it is in header now -->
              </div>
            </div>
          </div>
        </TransitionGroup>

        <div v-if="allActions.length === 0" class="waiting-state">
          <template v-if="phase === 2">
            <div class="pulse-ring muted"></div>
            <span class="waiting-hint">
              No saved actions found for this simulation. The run may have been reset, or action logs were cleared.
            </span>
          </template>
          <template v-else>
            <div class="pulse-ring"></div>
            <span>Waiting for agent actions...</span>
          </template>
        </div>
      </div>
    </div>

    <!-- Bottom Info / Logs -->
    <div class="system-logs">
      <div class="log-header">
        <span class="log-title">SIMULATION MONITOR</span>
        <span class="log-id">{{ simulationId || 'NO_SIMULATION' }}</span>
      </div>
      <div class="log-content" ref="logContent">
        <div class="log-line" v-for="(log, idx) in systemLogs" :key="idx">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="showCreditModal" class="credit-modal-overlay" @click.self="showCreditModal = false">
        <div class="credit-modal">
          <button class="credit-modal-close" @click="showCreditModal = false">&times;</button>
          <div class="credit-modal-icon">0</div>
          <h3 class="credit-modal-title">No Simulations Remaining</h3>
          <p class="credit-modal-desc">
            You need at least 1 simulation to run. Upgrade your plan or purchase additional simulations to continue your analysis.
          </p>
          <div class="credit-modal-actions">
            <router-link to="/pricing" class="credit-modal-btn primary">Upgrade Plan</router-link>
            <button class="credit-modal-btn secondary" @click="showCreditModal = false">Cancel</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { 
  startSimulation, 
  stopSimulation,
  getSimulation,
  getSimulationConfig,
  getRunStatus, 
  getRunStatusDetail
} from '../api/simulation'
import { generateReport } from '../api/report'
import { trackEvent } from '../lib/analytics'
import {
  step3StatusPollMs,
  step3DetailPollMs,
  graphSkipPollWhenDocumentHidden,
} from '../config/zepFootprint'

const GRAPH_MEMORY_SESSION_KEY = 'glas_pref_graph_memory'

function readGraphMemoryPref() {
  try {
    const v = sessionStorage.getItem(GRAPH_MEMORY_SESSION_KEY)
    if (v === 'true') return true
    if (v === 'false') return false
  } catch (_) {
    /* ignore */
  }
  return false
}

const props = defineProps({
  simulationId: String,
  maxRounds: Number,
  minutesPerRound: {
    type: Number,
    default: 30
  },
  /** Merged into simulation_config time_config on POST /start (from Step 2 confirm modal) */
  startTimeConfig: {
    type: Object,
    default: null,
  },
  projectData: Object,
  graphData: Object,
  systemLogs: Array,
  /** When true (e.g. bundle "Details"), load saved run from disk — do not POST /start */
  reviewMode: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status'])

const router = useRouter()

// State
const isGeneratingReport = ref(false)
const enableGraphMemoryUpdate = ref(readGraphMemoryPref())
const phase = ref(0)
const isStarting = ref(false)
const isStopping = ref(false)
const startError = ref(null)
const showCreditModal = ref(false)
const runStatus = ref({})
const allActions = ref([])
const actionIds = ref(new Set())
const scrollContainer = ref(null)
/** time_scale from simulation_config when run_state has not populated it yet */
const scheduleFromConfig = ref(null)

// Computed
const chronologicalActions = computed(() => {
  return allActions.value
})

const twitterActionsCount = computed(() => {
  return allActions.value.filter(a => a.platform === 'twitter').length
})

const redditActionsCount = computed(() => {
  return allActions.value.filter(a => a.platform === 'reddit').length
})

function normalizeTimeScale(raw) {
  if (!raw || typeof raw !== 'object' || raw.unit == null || raw.unit === '') return null
  const unit = String(raw.unit).toLowerCase()
  return {
    unit,
    per_round: Math.max(1, Number(raw.per_round) || 1),
    total_duration: raw.total_duration,
    start_date: raw.start_date || '',
  }
}

const timeScale = computed(() => {
  const fromRun = normalizeTimeScale(runStatus.value?.time_scale)
  if (fromRun) return fromRun
  const fromStart = normalizeTimeScale(props.startTimeConfig?.time_scale)
  if (fromStart) return fromStart
  if (scheduleFromConfig.value) return scheduleFromConfig.value
  return { unit: 'hour', per_round: 1, total_duration: undefined, start_date: '' }
})

const isHourlyScale = computed(() => (timeScale.value.unit || 'hour') === 'hour')

async function hydrateScheduleFromConfig() {
  scheduleFromConfig.value = null
  if (!props.simulationId) return
  try {
    const res = await getSimulationConfig(props.simulationId)
    if (res.success && res.data?.time_config?.time_scale) {
      const n = normalizeTimeScale(res.data.time_config.time_scale)
      if (n) scheduleFromConfig.value = n
    }
  } catch {
    /* e.g. 404 before prepare */
  }
}

watch(
  () => props.simulationId,
  (id) => {
    if (id) void hydrateScheduleFromConfig()
  }
)

/** Calendar-style simulated span: "0 months" … "6 months" (uses scenario time_scale). */
function formatCalendarElapsedUnits(totalUnits, unitRaw) {
  const u = String(unitRaw || 'month').toLowerCase()
  const n = Math.max(0, Math.floor(Number(totalUnits) || 0))
  const singular = { month: 'month', week: 'week', day: 'day', year: 'year' }[u] || u
  const plural = { month: 'months', week: 'weeks', day: 'days', year: 'years' }[u] || `${u}s`
  return `${n} ${n === 1 ? singular : plural}`
}

const elapsedTimeStatLabel = computed(() => {
  if (isHourlyScale.value) return 'Elapsed time'
  const u = String(timeScale.value.unit || 'timeline').toLowerCase()
  return `Simulated (${u}s)`
})

const formatElapsedTime = (currentRound) => {
  const r = Math.max(0, Number(currentRound) || 0)
  const ts = timeScale.value || {}
  const unit = String(ts.unit || 'hour').toLowerCase()
  const perRound = Math.max(1, Number(ts.per_round) || 1)

  if (unit === 'hour') {
    if (r <= 0) return '0h 0m'
    const mpr = Math.max(1, Number(props.minutesPerRound) || 60)
    const totalMinutes = r * mpr
    const hours = Math.floor(totalMinutes / 60)
    const minutes = Math.round(totalMinutes % 60)
    return `${hours}h ${minutes}m`
  }

  const elapsedUnits = r * perRound
  return formatCalendarElapsedUnits(elapsedUnits, unit)
}

const twitterElapsedTime = computed(() => {
  return formatElapsedTime(runStatus.value.twitter_current_round || 0)
})

const redditElapsedTime = computed(() => {
  return formatElapsedTime(runStatus.value.reddit_current_round || 0)
})

// Methods
const addLog = (msg) => {
  emit('add-log', msg)
}

const resetAllState = () => {
  phase.value = 0
  runStatus.value = {}
  allActions.value = []
  actionIds.value = new Set()
  prevTwitterRound.value = 0
  prevRedditRound.value = 0
  startError.value = null
  isStarting.value = false
  isStopping.value = false
  stopPolling()
}

/** Load completed run state + action timeline without starting a new subprocess */
const loadCompletedRun = async () => {
  if (!props.simulationId) return
  addLog('Loading saved simulation results (no restart)...')
  emit('update-status', 'processing')
  try {
    const res = await getRunStatus(props.simulationId)
    if (res.success && res.data) {
      runStatus.value = res.data
    }
    await fetchRunStatusDetail()
    phase.value = 2
    emit('update-status', 'completed')
    const n = allActions.value.length
    addLog(n > 0 ? `✓ Loaded ${n} actions from saved run` : '✓ Run loaded — no actions in storage (logs may be empty)')
  } catch (err) {
    addLog(`✗ Failed to load run: ${err.message || err}`)
    emit('update-status', 'error')
  }
}

/** Attach to an already-running worker process (no POST /start). */
const attachToLiveRun = async () => {
  if (!props.simulationId) return
  addLog('Attaching to simulation already in progress...')
  emit('update-status', 'processing')
  try {
    const res = await getRunStatus(props.simulationId)
    if (res.success && res.data) {
      runStatus.value = res.data
    }
    await fetchRunStatusDetail()
    phase.value = 1
    startStatusPolling()
    startDetailPolling()
  } catch (err) {
    addLog(`✗ Failed to attach: ${err.message || err}`)
    emit('update-status', 'error')
  }
}

const doStartSimulation = async () => {
  if (!props.simulationId) {
    addLog('Error: missing simulationId')
    return
  }
  
  resetAllState()
  
  isStarting.value = true
  startError.value = null
  addLog('Starting parallel simulation...')
  emit('update-status', 'processing')
  
  try {
    const params = {
      simulation_id: props.simulationId,
      platform: 'parallel',
      force: true,
      enable_graph_memory_update: !!enableGraphMemoryUpdate.value
    }

    const sessionId = localStorage.getItem('glas_active_session')
    if (sessionId) {
      params.session_id = sessionId
      localStorage.removeItem('glas_active_session')
    }
    
    if (props.maxRounds) {
      params.max_rounds = props.maxRounds
      addLog(`Max simulation rounds: ${props.maxRounds}`)
    }

    if (props.startTimeConfig && typeof props.startTimeConfig === 'object' && Object.keys(props.startTimeConfig).length) {
      try {
        params.time_config = JSON.parse(JSON.stringify(props.startTimeConfig))
      } catch {
        params.time_config = { ...props.startTimeConfig }
      }
      addLog('Applying confirmed timeline (time scale & rounds)')
    }
    
    const res = await startSimulation(params)
    
    if (res.success && res.data) {
      // Note: any falsy value (false or missing field) hits the "disabled" log. Use
      // res.data.graph_memory_update_enabled === true (and a separate branch) if you need
      // to distinguish explicitly disabled from omitted field.
      if (res.data.graph_memory_update_enabled) {
        addLog('Dynamic graph update mode enabled (Zep graph memory)')
      } else {
        addLog('Graph memory update disabled by server (no graph_id)')
      }
      if (res.data.force_restarted) {
        addLog('✓ Cleared old simulation logs, restarting')
      }
      addLog('✓ Simulation engine started')
      addLog(`  ├─ PID: ${res.data.process_pid || '-'}`)
      trackEvent('simulation_started', {
        simulation_id: props.simulationId,
        enable_graph_memory_update: !!enableGraphMemoryUpdate.value,
        graph_memory: !!enableGraphMemoryUpdate.value,
      })
      
      phase.value = 1
      runStatus.value = res.data
      
      startStatusPolling()
      startDetailPolling()
    } else {
      startError.value = res.error || 'Start failed'
      addLog(`✗ Start failed: ${res.error || 'Unknown error'}`)
      emit('update-status', 'error')
    }
  } catch (err) {
    const respData = err.response?.data
    const apiMsg = respData?.error || respData?.detail || err.message
    if (err.response?.status === 402 || respData?.error === 'insufficient_credits') {
      showCreditModal.value = true
      trackEvent('upgrade_prompt_shown', { trigger: 'insufficient_credits' })
      addLog('✗ Insufficient simulations remaining')
    } else {
      startError.value = apiMsg
      addLog(`✗ Start failed: ${apiMsg}`)
    }
    emit('update-status', 'error')
  } finally {
    isStarting.value = false
  }
}

const handleStopSimulation = async () => {
  if (!props.simulationId) return
  
  isStopping.value = true
  addLog('Stopping simulation...')
  
  try {
    const res = await stopSimulation({ simulation_id: props.simulationId })
    
    if (res.success) {
      addLog('✓ Simulation stopped')
      phase.value = 2
      stopPolling()
      emit('update-status', 'completed')
    } else {
      addLog(`Stop failed: ${res.error || 'Unknown error'}`)
    }
  } catch (err) {
    addLog(`Stop exception: ${err.message}`)
  } finally {
    isStopping.value = false
  }
}

let statusTimer = null
let detailTimer = null

const startStatusPolling = () => {
  statusTimer = setInterval(fetchRunStatus, step3StatusPollMs)
}

const startDetailPolling = () => {
  detailTimer = setInterval(fetchRunStatusDetail, step3DetailPollMs)
}

const stopPolling = () => {
  if (statusTimer) {
    clearInterval(statusTimer)
    statusTimer = null
  }
  if (detailTimer) {
    clearInterval(detailTimer)
    detailTimer = null
  }
}

const prevTwitterRound = ref(0)
const prevRedditRound = ref(0)

const fetchRunStatus = async () => {
  if (!props.simulationId) return
  if (graphSkipPollWhenDocumentHidden && document.hidden) return

  try {
    const res = await getRunStatus(props.simulationId)
    
    if (res.success && res.data) {
      const data = res.data
      
      runStatus.value = data
      
      if (data.twitter_current_round > prevTwitterRound.value) {
        const timeStr = data.current_time_label || `${data.twitter_simulated_hours || 0}h`
        addLog(`[Plaza] R${data.twitter_current_round}/${data.total_rounds} | T:${timeStr} | A:${data.twitter_actions_count}`)
        prevTwitterRound.value = data.twitter_current_round
      }
      
      if (data.reddit_current_round > prevRedditRound.value) {
        const timeStr = data.current_time_label || `${data.reddit_simulated_hours || 0}h`
        addLog(`[Community] R${data.reddit_current_round}/${data.total_rounds} | T:${timeStr} | A:${data.reddit_actions_count}`)
        prevRedditRound.value = data.reddit_current_round
      }
      
      const isCompleted = data.runner_status === 'completed' || data.runner_status === 'stopped'
      const platformsCompleted = checkPlatformsCompleted(data)
      
      if (isCompleted || platformsCompleted) {
        if (platformsCompleted && !isCompleted) {
          addLog('✓ All platform simulations completed')
        }
        addLog('✓ Simulation complete')
        phase.value = 2
        stopPolling()
        emit('update-status', 'completed')
      }
    }
  } catch (err) {
    console.warn('Fetch run status failed:', err)
  }
}

const checkPlatformsCompleted = (data) => {
  if (!data) return false
  
  const twitterCompleted = data.twitter_completed === true
  const redditCompleted = data.reddit_completed === true
  
  const twitterEnabled = (data.twitter_actions_count > 0) || data.twitter_running || twitterCompleted
  const redditEnabled = (data.reddit_actions_count > 0) || data.reddit_running || redditCompleted
  
  if (!twitterEnabled && !redditEnabled) return false
  
  if (twitterEnabled && !twitterCompleted) return false
  if (redditEnabled && !redditCompleted) return false
  
  return true
}

const fetchRunStatusDetail = async () => {
  if (!props.simulationId) return
  if (graphSkipPollWhenDocumentHidden && document.hidden) return

  try {
    const res = await getRunStatusDetail(props.simulationId)
    
    if (res.success && res.data) {
      const serverActions = res.data.all_actions || []
      
      let newActionsAdded = 0
      serverActions.forEach(action => {
        const actionId = action.id || `${action.timestamp}-${action.platform}-${action.agent_id}-${action.action_type}`
        
        if (!actionIds.value.has(actionId)) {
          actionIds.value.add(actionId)
          allActions.value.push({
            ...action,
            _uniqueId: actionId
          })
          newActionsAdded++
        }
      })
      
    }
  } catch (err) {
    console.warn('Fetch detail status failed:', err)
  }
}

// Helpers
const getActionTypeLabel = (type) => {
  if (type?.startsWith('TOOL_')) {
    const toolLabels = {
      'TOOL_WEB_SEARCH': 'SEARCH',
      'TOOL_LOOKUP_NEWS': 'NEWS',
      'TOOL_LOOKUP_FINANCIAL_DATA': 'FINANCE',
    }
    return toolLabels[type] || 'ACTION'
  }
  if (type?.startsWith('STATE_')) {
    const stateLabels = {
      'STATE_SUPPRESS_AGENT': 'SUPPRESS',
      'STATE_BOOST_AGENT': 'BOOST',
      'STATE_CREATE_LINK': 'ALLY',
      'STATE_BREAK_LINK': 'SEVER',
      'STATE_BROADCAST': 'BROADCAST',
    }
    return stateLabels[type] || 'EFFECT'
  }
  const labels = {
    'CREATE_POST': 'POST',
    'REPOST': 'REPOST',
    'LIKE_POST': 'LIKE',
    'CREATE_COMMENT': 'COMMENT',
    'LIKE_COMMENT': 'LIKE',
    'DO_NOTHING': 'IDLE',
    'FOLLOW': 'FOLLOW',
    'SEARCH_POSTS': 'SEARCH',
    'QUOTE_POST': 'QUOTE',
    'UPVOTE_POST': 'UPVOTE',
    'DOWNVOTE_POST': 'DOWNVOTE'
  }
  return labels[type] || type || 'UNKNOWN'
}

const getActionTypeClass = (type) => {
  if (type?.startsWith('TOOL_')) return 'badge-tool'
  if (type?.startsWith('STATE_')) return 'badge-state'
  const classes = {
    'CREATE_POST': 'badge-post',
    'REPOST': 'badge-action',
    'LIKE_POST': 'badge-action',
    'CREATE_COMMENT': 'badge-comment',
    'LIKE_COMMENT': 'badge-action',
    'QUOTE_POST': 'badge-post',
    'FOLLOW': 'badge-meta',
    'SEARCH_POSTS': 'badge-meta',
    'UPVOTE_POST': 'badge-action',
    'DOWNVOTE_POST': 'badge-action',
    'DO_NOTHING': 'badge-idle'
  }
  return classes[type] || 'badge-default'
}

const KNOWN_ACTION_TYPES = new Set([
  'CREATE_POST', 'QUOTE_POST', 'REPOST', 'LIKE_POST', 'CREATE_COMMENT',
  'SEARCH_POSTS', 'FOLLOW', 'UPVOTE_POST', 'DOWNVOTE_POST', 'DO_NOTHING'
])

const isKnownActionType = (type) => {
  return KNOWN_ACTION_TYPES.has(type) || type?.startsWith('TOOL_') || type?.startsWith('STATE_')
}

const getStateChangeLabel = (action) => {
  const effectType = action.action_args?.effect_type || ''
  const labels = {
    'suppress_agent': 'Activity Suppressed',
    'boost_agent': 'Activity Boosted',
    'create_link': 'Connection Formed',
    'break_link': 'Connection Severed',
    'broadcast': 'Broadcast',
  }
  return labels[effectType] || 'State Changed'
}

const getStateChangeDelta = (action) => {
  const before = action.action_args?.before
  const after = action.action_args?.after
  if (!before || !after) return ''
  if (before.activity_level != null && after.activity_level != null) {
    const pctBefore = Math.round(before.activity_level * 100)
    const pctAfter = Math.round(after.activity_level * 100)
    return `Activity: ${pctBefore}% → ${pctAfter}%`
  }
  if (after.follow_exists === true) return `New follow: ${after.direction || ''}`
  if (after.follow_exists === false) return `Unfollowed: ${before.direction || ''}`
  if (after.message) return after.message
  return ''
}

const getToolInput = (action) => {
  const args = action.action_args?.tool_args
  if (!args) return ''
  if (args.query) return args.query
  if (args.topic) return args.topic
  if (args.action_description) return args.action_description
  const fallback = JSON.stringify(args)
  return fallback.length > 120 ? fallback.slice(0, 120) + '…' : fallback
}

const truncateContent = (content, maxLength = 100) => {
  if (!content) return ''
  if (content.length > maxLength) return content.substring(0, maxLength) + '...'
  return content
}

const formatActionTime = (timestamp) => {
  if (!timestamp) return ''
  try {
    return new Date(timestamp).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}

const handleNextStep = async () => {
  if (!props.simulationId) {
    addLog('Error: missing simulationId')
    return
  }
  
  if (isGeneratingReport.value) {
    addLog('Report generation request already sent, please wait...')
    return
  }
  
  isGeneratingReport.value = true
  addLog('Starting report generation...')
  
  try {
    const res = await generateReport({
      simulation_id: props.simulationId,
      force_regenerate: true
    })
    
    if (res.success && res.data) {
      const reportId = res.data.report_id
      addLog(`✓ Report generation started: ${reportId}`)
      
      router.push({ name: 'Report', params: { reportId } })
    } else {
      addLog(`✗ Report generation failed: ${res.error || 'Unknown error'}`)
      isGeneratingReport.value = false
    }
  } catch (err) {
    addLog(`✗ Report generation exception: ${err.message}`)
    isGeneratingReport.value = false
  }
}

// Scroll log to bottom
const logContent = ref(null)
watch(() => props.systemLogs?.length, () => {
  nextTick(() => {
    if (logContent.value) {
      logContent.value.scrollTop = logContent.value.scrollHeight
    }
  })
})

watch(enableGraphMemoryUpdate, (v) => {
  try {
    sessionStorage.setItem(GRAPH_MEMORY_SESSION_KEY, v ? 'true' : 'false')
  } catch (_) {
    /* ignore */
  }
})

const onStep3Visibility = () => {
  if (document.hidden) return
  if (phase.value !== 1) return
  void fetchRunStatus()
  void fetchRunStatusDetail()
}

let preparingCancelled = false

onMounted(async () => {
  document.addEventListener('visibilitychange', onStep3Visibility)
  addLog('Step3 simulation runtime initializing')
  if (!props.simulationId) return

  await hydrateScheduleFromConfig()

  if (props.reviewMode) {
    await loadCompletedRun()
    return
  }

  let simData = null
  try {
    const simRes = await getSimulation(props.simulationId)
    if (simRes.success && simRes.data) {
      simData = simRes.data
    }
  } catch (e) {
    addLog(`Could not load simulation record: ${e.message || e}`)
  }

  if (simData?.status === 'preparing') {
    addLog('Preparing agents & config… will attach when ready (no restart)')
    emit('update-status', 'processing')
    for (let i = 0; i < 900; i++) {
      if (preparingCancelled) return
      await new Promise((r) => setTimeout(r, 2000))
      if (preparingCancelled) return
      try {
        const simRes = await getSimulation(props.simulationId)
        if (simRes.success && simRes.data) {
          simData = simRes.data
        }
      } catch {
        continue
      }
      if (!simData || simData.status !== 'preparing') {
        break
      }
    }
    if (simData?.status === 'preparing') {
      addLog('Still preparing — use bundle analysis page for full progress, or try again shortly')
      emit('update-status', 'error')
      return
    }
  }

  await hydrateScheduleFromConfig()

  let runData = null
  try {
    const runRes = await getRunStatus(props.simulationId)
    if (runRes.success && runRes.data) {
      runData = runRes.data
    }
  } catch (_) {
    /* fall through to start */
  }

  if (simData?.status === 'completed') {
    addLog('Simulation is completed — opening saved results (not restarting)')
    await loadCompletedRun()
    return
  }

  const rs = runData?.runner_status
  if (rs === 'completed' || rs === 'stopped' || rs === 'failed') {
    addLog(`Saved run on disk (${rs}) — loading timeline`)
    await loadCompletedRun()
    return
  }

  if (simData?.status === 'running' && rs === 'running') {
    await attachToLiveRun()
    return
  }

  doStartSimulation()
})

onUnmounted(() => {
  preparingCancelled = true
  document.removeEventListener('visibilitychange', onStep3Visibility)
  stopPolling()
})
</script>

<style scoped src="./Step3Simulation.scoped.css"></style>
