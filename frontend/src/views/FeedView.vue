<template>
  <div class="feed-container">
    <AppNavbar />

    <div class="feed-content">
      <header class="feed-header">
        <div class="header-tag">Intelligence Feed</div>
        <h1 class="header-title">Industry Intelligence Feed</h1>
        <p class="header-desc">
          Published scenario simulations across regulated industries.
          Free reports available. Subscribe for full access to all analyses.
        </p>
      </header>

      <div class="feed-controls">
        <div class="filter-group">
          <label class="filter-label">Industry</label>
          <select v-model="selectedIndustry" class="filter-select" @change="loadSimulations">
            <option value="">All Industries</option>
            <option v-for="ind in industries" :key="ind.id" :value="ind.id">
              {{ ind.name }} ({{ ind.country }})
            </option>
          </select>
        </div>
      </div>

      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
        <span>Loading feed...</span>
      </div>

      <div v-else-if="simulations.length === 0" class="empty-state">
        <div class="empty-icon">--</div>
        <h3>No reports published yet</h3>
        <p>Check back soon. New scenario intelligence is published regularly.</p>
      </div>

      <div v-else class="feed-grid">
        <article
          v-for="sim in simulations"
          :key="sim.id"
          class="feed-card"
          @click="viewSimulation(sim)"
        >
          <div class="card-top">
            <span class="industry-badge" :class="badgeClass(sim.industry_id)">
              {{ industryName(sim.industry_id) }}
            </span>
            <span class="card-date">{{ formatDate(sim.published_at) }}</span>
          </div>

          <h2 class="card-title">{{ sim.title }}</h2>

          <p class="card-summary" :class="{ expanded: expandedCard === sim.id }">
            {{ sim.summary || sim.scenario_description }}
          </p>

          <div class="card-footer">
            <template v-if="sim.access === 'full'">
              <button class="card-btn card-btn--primary" @click.stop="viewReport(sim)">
                Read Full Report <span class="btn-arrow">&rarr;</span>
              </button>
            </template>
            <template v-else>
              <div class="paywall-hint">
                <span class="lock-icon">&#9679;</span>
                Full report requires a subscription
              </div>
              <router-link to="/pricing" class="card-btn card-btn--subscribe" @click.stop>
                Subscribe to unlock
              </router-link>
            </template>
          </div>
        </article>
      </div>

      <div v-if="simulations.length > 0 && hasMore" class="load-more">
        <button class="load-more-btn" @click="loadMore" :disabled="loadingMore">
          {{ loadingMore ? 'Loading...' : 'Load More' }}
        </button>
      </div>
    </div>

    <!-- Login Prompt Modal -->
    <Teleport to="body">
      <div v-if="showLoginModal" class="login-modal-overlay" @click.self="showLoginModal = false">
        <div class="login-modal">
          <button class="login-modal-close" @click="showLoginModal = false">&times;</button>
          <div class="login-modal-icon">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          </div>
          <h3 class="login-modal-title">Create an account to read reports</h3>
          <p class="login-modal-desc">Sign up for free to access published scenario intelligence.</p>
          <div class="login-modal-actions">
            <button class="login-modal-btn primary" @click="router.push({ path: '/signup', query: { redirect: loginRedirectPath } })">Sign Up Free</button>
            <button class="login-modal-btn secondary" @click="router.push({ path: '/login', query: { redirect: loginRedirectPath } })">Log In</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'
import { authState } from '../store/auth'
import { supabase } from '../lib/supabase'
import AppNavbar from '../components/AppNavbar.vue'

const router = useRouter()
const { apiGet } = useApi()

const industries = ref([])
const simulations = ref([])
const selectedIndustry = ref('')
const isSubscriber = ref(false)
const loading = ref(true)
const loadingMore = ref(false)
const hasMore = ref(false)

const PAGE_SIZE = 20
let currentOffset = 0

const demoSimulations = [
  {
    id: 'demo-iran',
    industry_id: 'geopolitics',
    title: 'US-Iran Nuclear Conflict: 9-Scenario Impact Analysis',
    summary: 'Multi-agent simulation of military strike options on Iranian nuclear facilities. Nine scenarios analysed across five dimensions: Economic Sustainability, Social Cohesion, State Capacity, Long-term Resilience, and Democratic Legitimacy. Best option: Negotiated Deal (JCPOA 2.0) at +8.0. Full conflict scores -12.6.',
    scenario_description: 'Targeted military strikes on Iran\'s nuclear facilities at Natanz and Fordow following collapsed diplomatic channels.',
    published_at: '2026-01-30T12:00:00Z',
    is_published: true,
    access: 'full',
  },
  {
    id: 'demo-energy',
    industry_id: 'energy_uk',
    title: 'Impact of Removing the UK Energy Price Cap',
    summary: 'A multi-agent simulation exploring how suppliers, regulators, and consumers react to deregulated pricing. Stakeholder dynamics modelled across retail energy markets, regulatory bodies, and consumer advocacy groups over 12 months.',
    scenario_description: 'UK government removes the Ofgem energy price cap, allowing suppliers to set retail prices freely.',
    published_at: '2026-03-10T09:00:00Z',
    is_published: true,
    access: 'summary',
  },
  {
    id: 'demo-finance',
    industry_id: 'finance',
    title: 'Basel IV Implementation: Stakeholder Dynamics',
    summary: 'How banks, fintechs, and supervisory bodies adapt to new capital requirements over 18 months. Simulation covers credit risk modelling changes, operational risk recalibration, and competitive dynamics between traditional banks and digital challengers.',
    scenario_description: 'Full Basel IV implementation across EU and UK jurisdictions with standardised approach mandates.',
    published_at: '2026-02-20T14:00:00Z',
    is_published: true,
    access: 'summary',
  },
]

const demoIndustries = [
  { id: 'geopolitics', name: 'Geopolitics', country: 'Global' },
  { id: 'energy_uk', name: 'Energy & Utilities', country: 'UK' },
  { id: 'energy_us', name: 'Energy & Utilities', country: 'US' },
  { id: 'finance', name: 'Finance & Banking', country: 'Global' },
]

async function loadIndustries() {
  try {
    const res = await apiGet('/feed/industries')
    if (res.success && res.data?.length > 0) {
      industries.value = res.data
      return
    }
  } catch (e) { /* fall through */ }
  industries.value = demoIndustries
}

/** Sync Supabase session into authState so API requests send a fresh Bearer token (fixes feed paywall after login). */
async function syncSessionForApi() {
  if (!supabase) return
  try {
    const { data: { session } } = await supabase.auth.getSession()
    if (session) authState.session = session
  } catch (_) { /* ignore */ }
}

async function loadSimulations() {
  await syncSessionForApi()
  loading.value = true
  currentOffset = 0
  const params = new URLSearchParams({ limit: PAGE_SIZE, offset: 0 })
  if (selectedIndustry.value) params.set('industry_id', selectedIndustry.value)

  try {
    const res = await apiGet(`/feed/simulations?${params}`)
    if (res.success && res.data?.length > 0) {
      simulations.value = res.data
      isSubscriber.value = !!res.plan && res.plan !== 'free'
      hasMore.value = res.count >= PAGE_SIZE
      currentOffset = res.count
      loading.value = false
      return
    }
  } catch (e) { /* fall through */ }

  let items = [...demoSimulations]
  if (selectedIndustry.value) {
    items = items.filter(s => s.industry_id === selectedIndustry.value)
  }
  simulations.value = items
  isSubscriber.value = false
  hasMore.value = false
  loading.value = false
}

async function loadMore() {
  await syncSessionForApi()
  loadingMore.value = true
  const params = new URLSearchParams({ limit: PAGE_SIZE, offset: currentOffset })
  if (selectedIndustry.value) params.set('industry_id', selectedIndustry.value)

  const res = await apiGet(`/feed/simulations?${params}`)
  if (res.success) {
    simulations.value.push(...res.data)
    hasMore.value = res.count >= PAGE_SIZE
    currentOffset += res.count
  }
  loadingMore.value = false
}

const expandedCard = ref(null)
const showLoginModal = ref(false)
const loginRedirectPath = ref('')

function viewSimulation(sim) {
  if (sim.access === 'full') {
    viewReport(sim)
  } else {
    expandedCard.value = expandedCard.value === sim.id ? null : sim.id
  }
}

function viewReport(sim) {
  const targetPath = sim.id?.startsWith('demo-')
    ? `/feed/report/${sim.id}`
    : sim.report_id ? `/report/${sim.report_id}` : null
  if (!targetPath) return

  if (!authState.user) {
    loginRedirectPath.value = targetPath
    showLoginModal.value = true
    return
  }

  router.push(targetPath)
}

function industryName(id) {
  const ind = industries.value.find(i => i.id === id)
  return ind ? `${ind.name}` : id || 'General'
}

function badgeClass(id) {
  if (!id) return ''
  if (id.startsWith('energy')) return 'badge-energy'
  if (id === 'geopolitics') return 'badge-geopolitics'
  if (id === 'finance') return 'badge-finance'
  return ''
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

onMounted(() => {
  loadIndustries()
  loadSimulations()
})

// Reload feed when auth session token changes (e.g. after login redirect) so plan/access is correct
watch(
  () => authState.session?.access_token,
  (newTok, oldTok) => {
    if (newTok && newTok !== oldTok) {
      loadSimulations()
    }
  },
)
</script>

<style scoped>
.feed-container {
  min-height: 100vh;
  background: #0a0a0a;
  color: #fff;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.feed-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 60px 40px 100px;
}

.feed-header {
  margin-bottom: 48px;
}

.header-tag {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 0.75rem;
  font-weight: 600;
  color: #4ade80;
  letter-spacing: 2px;
  text-transform: uppercase;
  margin-bottom: 16px;
}

.header-title {
  font-size: 2.8rem;
  font-weight: 700;
  margin: 0 0 16px 0;
  letter-spacing: -0.02em;
}

.header-desc {
  color: #888;
  font-size: 1.05rem;
  line-height: 1.6;
  max-width: 640px;
}

.feed-controls {
  margin-bottom: 40px;
  display: flex;
  gap: 20px;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.filter-label {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 0.75rem;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.filter-select {
  background: #1a1a1a;
  color: #fff;
  border: 1px solid #333;
  padding: 10px 16px;
  font-size: 0.9rem;
  font-family: inherit;
  border-radius: 0;
  cursor: pointer;
  min-width: 220px;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23666' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
}

.filter-select:focus {
  outline: none;
  border-color: #4ade80;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 80px 0;
  color: #666;
  font-size: 0.95rem;
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #333;
  border-top-color: #4ade80;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-state {
  text-align: center;
  padding: 100px 20px;
  color: #666;
}

.empty-icon {
  font-size: 2rem;
  color: #333;
  margin-bottom: 20px;
}

.empty-state h3 {
  font-size: 1.3rem;
  font-weight: 500;
  color: #999;
  margin: 0 0 8px 0;
}

.empty-state p {
  font-size: 0.95rem;
  margin: 0;
}

.feed-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 24px;
}

.feed-card {
  background: #1a1a1a;
  border: 1px solid #333;
  padding: 28px;
  display: flex;
  flex-direction: column;
  transition: border-color 0.2s, transform 0.2s;
  cursor: pointer;
}

.feed-card:hover {
  border-color: #555;
  transform: translateY(-2px);
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.industry-badge {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 0.7rem;
  font-weight: 600;
  padding: 4px 10px;
  background: #262626;
  color: #999;
  letter-spacing: 0.5px;
}

.badge-energy {
  background: rgba(74, 222, 128, 0.1);
  color: #4ade80;
  border: 1px solid rgba(74, 222, 128, 0.2);
}

.badge-geopolitics {
  background: rgba(248, 113, 113, 0.1);
  color: #f87171;
  border: 1px solid rgba(248, 113, 113, 0.2);
}

.badge-finance {
  background: rgba(96, 165, 250, 0.1);
  color: #60a5fa;
  border: 1px solid rgba(96, 165, 250, 0.2);
}

.card-date {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #555;
}

.card-title {
  font-size: 1.25rem;
  font-weight: 600;
  margin: 0 0 14px 0;
  line-height: 1.4;
  color: #f0f0f0;
}

.card-summary {
  font-size: 0.9rem;
  color: #888;
  line-height: 1.7;
  flex: 1;
  margin: 0 0 20px 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  transition: all 0.3s;
}

.card-summary.expanded {
  -webkit-line-clamp: unset;
  display: block;
}

.card-footer {
  border-top: 1px solid #262626;
  padding-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.card-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 20px;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.5px;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
  text-decoration: none;
  text-align: center;
}

.card-btn--primary {
  background: #fff;
  color: #000;
}

.card-btn--primary:hover {
  background: #4ade80;
  color: #000;
}

.card-btn--subscribe {
  background: transparent;
  border: 1px solid #4ade80;
  color: #4ade80;
}

.card-btn--subscribe:hover {
  background: #4ade80;
  color: #000;
}

.btn-arrow {
  font-size: 1rem;
}

.paywall-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  color: #555;
}

.lock-icon {
  font-size: 0.5rem;
  color: #ff4500;
}

.free-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  color: #4ade80;
}

.free-icon {
  font-size: 0.5rem;
  color: #4ade80;
}

.load-more {
  display: flex;
  justify-content: center;
  margin-top: 48px;
}

.load-more-btn {
  background: transparent;
  border: 1px solid #333;
  color: #999;
  padding: 14px 40px;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
}

.load-more-btn:hover:not(:disabled) {
  border-color: #666;
  color: #fff;
}

.load-more-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .feed-content {
    padding: 40px 20px 80px;
  }

  .header-title {
    font-size: 2rem;
  }

  .feed-grid {
    grid-template-columns: 1fr;
  }
}

/* Login Prompt Modal */
.login-modal-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0, 0, 0, 0.7); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.login-modal {
  background: #1a1a1a; border: 1px solid #333;
  border-radius: 16px; padding: 40px; max-width: 400px; width: 90%;
  text-align: center; position: relative;
}
.login-modal-close {
  position: absolute; top: 12px; right: 16px;
  background: none; border: none; color: #888; font-size: 24px; cursor: pointer;
}
.login-modal-close:hover { color: #fff; }
.login-modal-icon { margin-bottom: 16px; color: #00b894; }
.login-modal-title { font-size: 1.15rem; font-weight: 700; margin-bottom: 8px; color: #fff; }
.login-modal-desc { font-size: 0.9rem; color: #999; line-height: 1.6; margin-bottom: 24px; }
.login-modal-actions { display: flex; flex-direction: column; gap: 10px; }
.login-modal-btn {
  padding: 14px 20px; border-radius: 8px; font-weight: 600; font-size: 0.95rem;
  cursor: pointer; border: none; transition: all 0.2s;
}
.login-modal-btn.primary { background: #00b894; color: #000; }
.login-modal-btn.primary:hover { filter: brightness(1.1); }
.login-modal-btn.secondary { background: transparent; border: 1px solid #333; color: #999; }
.login-modal-btn.secondary:hover { border-color: #00b894; color: #fff; }
</style>
