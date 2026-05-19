<template>
  <div class="dashboard-container">
    <AppNavbar />

    <div class="dash-content">
      <!-- Welcome Banner -->
      <header class="dash-header">
        <div class="header-tag">Dashboard</div>
        <h1 class="header-title">
          Welcome back<span v-if="profile.display_name">, {{ profile.display_name }}</span>
        </h1>
        <p class="header-plan">
          <span class="plan-badge" :class="'plan-' + profile.plan">{{ planLabel }}</span>
        </p>
      </header>

      <!-- Loading -->
      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
        <span>Loading dashboard...</span>
      </div>

      <div v-else-if="dashError" class="dash-error">{{ dashError }}</div>

      <template v-else>
        <!-- Simulation Allowance Banner -->
        <div v-if="profile.credits === 0 && profile.plan !== 'free'" class="credit-banner danger">
          <span class="banner-text">You've used all your simulations. Upgrade or buy more to continue your analysis.</span>
          <router-link to="/pricing" class="banner-action">Upgrade Now</router-link>
        </div>
        <div v-else-if="profile.credits > 0 && profile.credits <= 2 && profile.plan !== 'free'" class="credit-banner warning">
          <span class="banner-text">{{ profile.credits }} simulation{{ profile.credits > 1 ? 's' : '' }} remaining. A full decision analysis needs 3-5 simulations.</span>
          <router-link to="/pricing" class="banner-action">Get More Simulations</router-link>
        </div>

        <!-- Re-engagement Prompt -->
        <div v-if="daysSinceLastSim > 3 && recentSimulations.length > 0" class="reengagement-prompt">
          <span>Your last simulation was {{ daysSinceLastSim }} days ago.</span>
          <router-link to="/" class="prompt-action">Re-run with updated data</router-link>
        </div>

        <!-- Stats Cards -->
        <section class="stats-row">
          <div class="stat-card">
            <div class="stat-value">{{ profile.credits }}</div>
            <div class="stat-label">Simulations Remaining</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ simulationsThisMonth }}</div>
            <div class="stat-label">Simulations This Month</div>
          </div>
          <div class="stat-card">
            <div class="stat-value accent">{{ planLabel }}</div>
            <div class="stat-label">Current Plan</div>
          </div>
        </section>

        <!-- Quick Actions -->
        <section class="actions-row">
          <router-link to="/" class="action-btn primary">+ New Simulation</router-link>
          <router-link to="/pricing" class="action-btn">Buy Simulations</router-link>
          <router-link to="/feed" class="action-btn">View Feed</router-link>
        </section>

        <!-- Your Sessions -->
        <section v-if="recentSessions.length > 0" class="dash-section">
          <h2 class="section-heading">Your Sessions</h2>
          <div class="session-list">
            <div v-for="sess in recentSessions" :key="sess.id" class="session-row">
              <div class="session-info">
                <span class="session-prompt">{{ truncate(sess.prompt || 'Untitled session', 72) }}</span>
                <span class="session-meta">
                  <span class="session-date">{{ formatDate(sess.created_at) }}</span>
                  <span class="session-status-badge" :class="'status-' + sessionStatusClass(sess)">{{ sessionStatusLabel(sess) }}</span>
                </span>
              </div>
              <div class="session-actions">
                <button v-if="sess.project_id" class="step-link" @click.stop="goToStep(sess, 'graph')">Graph</button>
                <button v-if="sess.simulation_id" class="step-link" @click.stop="goToStep(sess, 'simulation')">Simulation</button>
                <button v-if="bundleIdOf(sess)" class="step-link" @click.stop="goToStep(sess, 'bundle')">Bundle</button>
                <button class="resume-btn" @click="resumeSession(sess)">Resume →</button>
              </div>
            </div>
          </div>
        </section>

        <!-- Decision Bundles -->
        <section v-if="bundles.length > 0" class="dash-section">
          <h2 class="section-heading">Decision Bundles</h2>
          <div class="bundle-list">
            <router-link
              v-for="b in bundles"
              :key="b.id"
              :to="{ name: 'BundleResults', params: { bundleId: b.id } }"
              class="bundle-row is-clickable"
            >
              <div class="bundle-info">
                <span class="bundle-title">{{ b.title }}</span>
                <span
                  class="bundle-timestamp"
                  :title="formatAbsolute(b.created_at)"
                >Created {{ formatRelative(b.created_at) }}</span>
                <span class="bundle-progress-text">{{ b.progress?.completed || 0 }} of {{ b.progress?.total || 0 }} scenarios</span>
              </div>
              <div class="bundle-bar-wrap">
                <div class="bundle-bar" :style="{ width: bundlePct(b) + '%' }"></div>
              </div>
              <span class="bundle-status-tag" :class="'status-' + b.status">{{ b.status === 'completed' ? 'Done' : 'In Progress' }}</span>
            </router-link>
          </div>
        </section>

        <!-- Upcoming Reminders -->
        <section v-if="reminders.length > 0" class="dash-section">
          <h2 class="section-heading">Upcoming Reminders</h2>
          <div class="reminder-list">
            <div v-for="r in reminders" :key="r.id" class="reminder-row">
              <div class="reminder-info">
                <span class="reminder-scenario">{{ r.scenario || 'Unnamed scenario' }}</span>
                <span class="reminder-date">{{ formatDate(r.remind_at) }}</span>
              </div>
            </div>
          </div>
        </section>

        <!-- Recent Simulations -->
        <section class="dash-section">
          <h2 class="section-heading">Recent Simulations</h2>
          <div v-if="recentSimulations.length === 0" class="empty-block">
            <p>No simulations yet. Run your first scenario to get started.</p>
          </div>
          <div v-else class="sim-list">
            <div
              v-for="sim in recentSimulations"
              :key="sim.id"
              class="sim-row"
              @click="viewSimulation(sim)"
            >
              <div class="sim-info">
                <span class="sim-title">{{ sim.title || sim.id }}</span>
                <span class="sim-date">{{ formatDate(sim.created_at) }}</span>
              </div>
              <span class="sim-status" :class="'status-' + sim.status">{{ sim.status }}</span>
            </div>
          </div>
        </section>

        <!-- Simulation History -->
        <section class="dash-section">
          <h2 class="section-heading">Simulation History</h2>
          <div v-if="creditHistory.length === 0" class="empty-block">
            <p>No simulation transactions yet.</p>
          </div>
          <table v-else class="credit-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Type</th>
                <th>Amount</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="tx in creditHistory" :key="tx.id">
                <td>{{ formatDate(tx.created_at) }}</td>
                <td><span class="tx-type" :class="'tx-' + tx.type">{{ tx.type }}</span></td>
                <td :class="tx.amount > 0 ? 'positive' : 'negative'">
                  {{ tx.amount > 0 ? '+' : '' }}{{ tx.amount }}
                </td>
                <td>{{ tx.description || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'
import { authState } from '../store/auth'
import { listBundles, listReminders, getRecentSessions } from '../api/simulation'
import { formatRelative, formatAbsolute } from '../utils/formatTime'
import AppNavbar from '../components/AppNavbar.vue'

const router = useRouter()
const { apiGet } = useApi()

const loading = ref(true)
const dashError = ref('')
const profile = ref({ email: '', display_name: '', plan: 'free', credits: 0 })
const recentSimulations = ref([])
const creditHistory = ref([])
const simulationsThisMonth = ref(0)
const bundles = ref([])
const reminders = ref([])
const recentSessions = ref([])

const planLabel = computed(() => {
  const labels = { free: 'Free', pro: 'Pro', business: 'Business', enterprise: 'Enterprise', payg: 'Pay-as-you-go' }
  return labels[profile.value.plan] || profile.value.plan
})

const daysSinceLastSim = computed(() => {
  if (recentSimulations.value.length === 0) return 0
  const last = recentSimulations.value[0]?.created_at
  if (!last) return 0
  const diff = Date.now() - new Date(last).getTime()
  return Math.floor(diff / (1000 * 60 * 60 * 24))
})

const bundlePct = (b) => {
  const total = b.progress?.total || 1
  const completed = b.progress?.completed || 0
  return Math.round((completed / total) * 100)
}

async function loadDashboard() {
  loading.value = true
  try {
    const [overviewRes, usageRes] = await Promise.all([
      apiGet('/dashboard/overview'),
      apiGet('/dashboard/usage'),
    ])

    if (overviewRes.success) {
      profile.value = overviewRes.data.profile
      recentSimulations.value = overviewRes.data.recent_simulations || []
      creditHistory.value = overviewRes.data.credit_history || []
    }

    if (usageRes.success) {
      simulationsThisMonth.value = usageRes.data.simulations_this_month
    }

    try {
      const bundleRes = await listBundles()
      if (bundleRes.data) bundles.value = bundleRes.data
    } catch { /* bundles table may not exist yet */ }

    try {
      const reminderRes = await listReminders()
      if (reminderRes.data) reminders.value = reminderRes.data
    } catch { /* reminders table may not exist yet */ }

    try {
      const sessRes = await getRecentSessions()
      if (sessRes?.data) recentSessions.value = sessRes.data
    } catch { /* non-critical */ }
  } catch (e) {
    console.error('Dashboard load failed:', e)
    dashError.value = 'Failed to load dashboard data'
  } finally {
    loading.value = false
  }
}

function viewSimulation(sim) {
  router.push(`/simulation/${sim.id}`)
}

function bundleIdOf(sess) {
  return sess.bundle_config?.bundle_id || null
}

function truncate(str, len) {
  if (!str || str.length <= len) return str
  return str.slice(0, len) + '…'
}

function sessionStatusClass(sess) {
  const rs = sess.research_status
  if (rs === 'processing' || rs === 'queued' || rs === 'claiming') return 'running'
  if (sess.status === 'completed') return 'completed'
  if (sess.status === 'sim_failed') return 'failed'
  if (sess.status === 'simulating') return 'running'
  return 'pending'
}

function sessionStatusLabel(sess) {
  const rs = sess.research_status
  if (rs === 'processing' || rs === 'queued' || rs === 'claiming') return 'Researching'
  if (rs === 'failed') return 'Research Failed'
  const bc = sess.bundle_config
  if (bc?.full_analysis) {
    if (sess.status === 'simulating') return 'Running Analysis'
    if (sess.status === 'completed') return 'Analysis Complete'
    if (sess.status === 'sim_failed') return 'Analysis Failed'
  }
  if (sess.status === 'research_complete') return 'Research Done'
  if (sess.status === 'simulating') return 'Simulating'
  if (sess.status === 'completed') return 'Completed'
  if (sess.status === 'sim_failed') return 'Sim Failed'
  return 'Active'
}

function goToStep(sess, step) {
  if (step === 'graph' && sess.project_id) {
    router.push({ name: 'Process', params: { projectId: sess.project_id }, query: { session_id: sess.id } })
  } else if (step === 'simulation' && sess.simulation_id) {
    router.push({ name: 'SimulationRun', params: { simulationId: sess.simulation_id } })
  } else if (step === 'bundle') {
    const bundleId = bundleIdOf(sess)
    if (bundleId) router.push({ name: 'BundleResults', params: { bundleId } })
  }
}

function resumeSession(sess) {
  const navStatus = ['simulating', 'completed', 'sim_failed']
  const bundleId = bundleIdOf(sess)
  if (navStatus.includes(sess.status) && bundleId) {
    router.push({ name: 'BundleResults', params: { bundleId } })
    return
  }
  if (navStatus.includes(sess.status) && sess.simulation_id) {
    router.push({ name: 'SimulationRun', params: { simulationId: sess.simulation_id } })
    return
  }
  if (sess.project_id) {
    router.push({ name: 'Process', params: { projectId: sess.project_id }, query: { session_id: sess.id } })
    return
  }
  localStorage.setItem('glas_active_session', sess.id)
  router.push('/')
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

onMounted(() => {
  if (authState.user) {
    profile.value.display_name = authState.user.user_metadata?.display_name || ''
    profile.value.email = authState.user.email || ''
  }
  loadDashboard()
})
</script>

<style scoped>
.dashboard-container {
  min-height: 100vh;
  background: #0a0a0a;
  color: #e0e0e0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.dash-content {
  max-width: 960px;
  margin: 0 auto;
  padding: 48px 24px 80px;
}

.dash-header {
  margin-bottom: 40px;
}

.header-tag {
  display: inline-block;
  font-size: 11px;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: #00c853;
  margin-bottom: 12px;
}

.header-title {
  font-size: 28px;
  font-weight: 600;
  color: #fff;
  margin: 0 0 12px;
  letter-spacing: -0.02em;
}

.plan-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.05em;
}

.plan-free {
  background: #1a1a1a;
  color: #888;
}

.plan-pro {
  background: rgba(0, 200, 83, 0.15);
  color: #00c853;
}

.plan-business {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

.plan-payg {
  background: rgba(168, 85, 247, 0.15);
  color: #a855f7;
}

.plan-professional, .plan-pro {
  background: rgba(255, 152, 0, 0.15);
  color: #ff9800;
}

.dash-error {
  text-align: center;
  color: #ff6b6b;
  font-size: 14px;
  padding: 24px;
  font-family: var(--font-mono);
}

/* Loading */
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 80px 0;
  color: #888;
  font-size: 14px;
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #333;
  border-top-color: #00c853;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Stats */
.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 32px;
}

.stat-card {
  background: #111;
  border: 1px solid #1e1e1e;
  border-radius: 8px;
  padding: 24px;
  text-align: center;
}

.stat-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 32px;
  font-weight: 700;
  color: #fff;
  margin-bottom: 4px;
}

.stat-value.accent {
  font-size: 18px;
  color: #00c853;
}

.stat-label {
  font-size: 12px;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

/* Actions */
.actions-row {
  display: flex;
  gap: 12px;
  margin-bottom: 48px;
}

.action-btn {
  padding: 10px 24px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  border: 1px solid #2a2a2a;
  color: #ccc;
  background: #111;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  border-color: #444;
  color: #fff;
}

.action-btn.primary {
  background: #00c853;
  color: #000;
  border-color: #00c853;
}

.action-btn.primary:hover {
  background: #00e676;
}

/* Sections */
.dash-section {
  margin-bottom: 48px;
}

.section-heading {
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  margin: 0 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #1a1a1a;
  letter-spacing: -0.02em;
}

.empty-block {
  padding: 32px;
  text-align: center;
  color: #555;
  font-size: 14px;
  background: #111;
  border-radius: 8px;
  border: 1px solid #1e1e1e;
}

/* Simulation List */
.sim-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: #1a1a1a;
  border-radius: 8px;
  overflow: hidden;
}

.sim-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  background: #111;
  cursor: pointer;
  transition: background 0.15s;
}

.sim-row:hover {
  background: #161616;
}

.sim-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sim-title {
  font-size: 14px;
  color: #e0e0e0;
  font-weight: 500;
}

.sim-date {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #555;
}

.sim-status {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 3px 10px;
  border-radius: 4px;
}

.status-completed {
  background: rgba(0, 200, 83, 0.12);
  color: #00c853;
}

.status-running, .status-processing {
  background: rgba(33, 150, 243, 0.12);
  color: #42a5f5;
}

.status-failed {
  background: rgba(244, 67, 54, 0.12);
  color: #ef5350;
}

.status-pending {
  background: rgba(255, 152, 0, 0.12);
  color: #ff9800;
}

/* Sessions */
.session-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: #1a1a1a;
  border-radius: 8px;
  overflow: hidden;
}

.session-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 20px;
  background: #111;
  transition: background 0.15s;
}

.session-row:hover {
  background: #161616;
}

.session-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.session-prompt {
  font-size: 13px;
  color: #e0e0e0;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.session-date {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #555;
}

.session-status-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 2px 8px;
  border-radius: 4px;
}

.session-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.step-link {
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
  color: #888;
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}

.step-link:hover {
  color: #ccc;
  border-color: #444;
  background: #222;
}

.resume-btn {
  padding: 5px 14px;
  font-size: 12px;
  font-weight: 600;
  color: #000;
  background: #00c853;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  transition: background 0.15s;
  font-family: inherit;
}

.resume-btn:hover {
  background: #00e676;
}

/* Credit Table */
.credit-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.credit-table th {
  text-align: left;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #555;
  padding: 8px 12px;
  border-bottom: 1px solid #1e1e1e;
}

.credit-table td {
  padding: 10px 12px;
  border-bottom: 1px solid #141414;
  color: #bbb;
}

.tx-type {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 3px;
}

.tx-usage {
  background: rgba(244, 67, 54, 0.1);
  color: #ef5350;
}

.tx-purchase, .tx-credit {
  background: rgba(0, 200, 83, 0.1);
  color: #00c853;
}

.positive {
  color: #00c853;
}

.negative {
  color: #ef5350;
}

/* Credit Banners */
.credit-banner {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px; border-radius: 8px; margin-bottom: 20px; gap: 12px;
}
.credit-banner.danger {
  background: rgba(244, 67, 54, 0.08); border: 1px solid rgba(244, 67, 54, 0.25);
}
.credit-banner.warning {
  background: rgba(255, 152, 0, 0.08); border: 1px solid rgba(255, 152, 0, 0.25);
}
.banner-text { font-size: 13px; color: #ccc; }
.banner-action {
  white-space: nowrap; font-size: 12px; font-weight: 600; color: #00c853;
  text-decoration: none; padding: 6px 14px; border-radius: 5px;
  border: 1px solid rgba(0,200,83,0.3);
}
.banner-action:hover { background: rgba(0,200,83,0.1); }

/* Re-engagement */
.reengagement-prompt {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 16px; border-radius: 8px; margin-bottom: 20px;
  background: rgba(33, 150, 243, 0.06); border: 1px solid rgba(33, 150, 243, 0.15);
  font-size: 13px; color: #999;
}
.prompt-action { color: #42a5f5; font-weight: 600; text-decoration: none; }
.prompt-action:hover { text-decoration: underline; }

/* Decision Bundles */
.bundle-list { display: flex; flex-direction: column; gap: 1px; background: #1a1a1a; border-radius: 8px; overflow: hidden; }
.bundle-row {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 14px 20px;
  background: #111;
  text-decoration: none;
  color: inherit;
  transition: background 0.15s;
}
.bundle-row.is-clickable {
  cursor: pointer;
}
.bundle-row:hover {
  background: rgba(255, 255, 255, 0.04);
}
.bundle-row:focus-visible {
  outline: 2px solid #00c853;
  outline-offset: 2px;
}
.bundle-info { flex: 1; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.bundle-title { font-size: 13px; color: #e0e0e0; font-weight: 500; }
.bundle-timestamp {
  font-size: 12px;
  color: #888;
}
.bundle-progress-text { font-size: 11px; color: #666; font-family: 'JetBrains Mono', monospace; }
.bundle-bar-wrap {
  width: 80px; height: 4px; background: #222; border-radius: 2px; overflow: hidden;
}
.bundle-bar { height: 100%; background: #00c853; border-radius: 2px; transition: width 0.3s; }
.bundle-status-tag {
  font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em;
  padding: 2px 8px; border-radius: 4px;
}

/* Reminders */
.reminder-list { display: flex; flex-direction: column; gap: 1px; background: #1a1a1a; border-radius: 8px; overflow: hidden; }
.reminder-row { padding: 12px 20px; background: #111; }
.reminder-info { display: flex; justify-content: space-between; }
.reminder-scenario { font-size: 13px; color: #ccc; }
.reminder-date { font-size: 12px; color: #666; font-family: 'JetBrains Mono', monospace; }

@media (max-width: 640px) {
  .stats-row {
    grid-template-columns: 1fr;
  }

  .actions-row {
    flex-direction: column;
  }

  .dash-content {
    padding: 32px 16px 60px;
  }

  .credit-banner { flex-direction: column; text-align: center; }
}
</style>
