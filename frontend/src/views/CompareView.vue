<template>
  <div class="compare-container">
    <AppNavbar />

    <div class="compare-content">
      <header class="compare-header">
        <div class="header-tag">Scenario Comparison</div>
        <h1 class="header-title">Side-by-Side Analysis</h1>
        <p class="header-desc">{{ scenarios.length }} scenarios compared</p>
      </header>

      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
        <span>Loading comparison...</span>
      </div>

      <div v-else-if="scenarios.length === 0" class="empty-state">
        <p>No report data available for comparison.</p>
        <router-link to="/" class="back-link">Go back</router-link>
      </div>

      <template v-else>
        <div class="compare-grid" :style="{ gridTemplateColumns: `repeat(${scenarios.length}, 1fr)` }">
          <div v-for="s in scenarios" :key="s.report_id" class="compare-card">
            <div class="card-header">
              <span class="card-label">Scenario</span>
              <h3 class="card-title">{{ s.title }}</h3>
            </div>

            <div class="card-verdict">
              <span class="verdict-label">Verdict</span>
              <span class="verdict-value" :class="verdictClass(s.verdict)">{{ s.verdict }}</span>
              <span class="confidence-badge">{{ s.confidence }} confidence</span>
            </div>

            <div class="card-section" v-if="s.key_drivers?.length">
              <h4>Key Drivers</h4>
              <div class="driver-list">
                <div v-for="(d, i) in s.key_drivers" :key="i" class="driver-item">
                  <span class="driver-name">{{ d.name }}</span>
                  <span class="driver-dir" :class="'dir-' + d.direction">{{ d.direction }}</span>
                  <span class="driver-mag">{{ d.magnitude }}</span>
                </div>
              </div>
            </div>

            <div class="card-section" v-if="s.scenarios_tested?.length">
              <h4>Scenarios Tested</h4>
              <ul class="tested-list">
                <li v-for="(name, i) in s.scenarios_tested" :key="i">{{ name }}</li>
              </ul>
            </div>

            <router-link :to="'/report/' + s.report_id" class="view-report-link">View Full Report</router-link>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AppNavbar from '../components/AppNavbar.vue'
import { compareReports } from '../api/simulation'
import { trackEvent } from '../lib/analytics'

const route = useRoute()

const loading = ref(true)
const scenarios = ref([])

const verdictClass = (verdict) => {
  const v = (verdict || '').toLowerCase().trim()
  if (/\bno[- ]?go\b/.test(v)) return 'verdict-nogo'
  if (/\bgo\b/.test(v)) return 'verdict-go'
  return 'verdict-caution'
}

onMounted(async () => {
  const ids = (route.query.ids || '').split(',').filter(Boolean)
  if (ids.length < 2) { loading.value = false; return }

  try {
    const res = await compareReports({ report_ids: ids })
    if (res.data?.scenarios) {
      scenarios.value = res.data.scenarios
      trackEvent('scenario_compared', { count: scenarios.value.length })
    }
  } catch (e) {
    console.error('Comparison failed:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.compare-container {
  min-height: 100vh; background: #0a0a0a; color: #e0e0e0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
.compare-content { max-width: 1200px; margin: 0 auto; padding: 48px 24px 80px; }
.compare-header { margin-bottom: 36px; }
.header-tag {
  font-size: 11px; letter-spacing: 0.15em; text-transform: uppercase;
  color: #00c853; margin-bottom: 10px;
}
.header-title { font-size: 24px; font-weight: 600; color: #fff; margin: 0 0 6px; }
.header-desc { font-size: 14px; color: #888; margin: 0; }

.loading-state {
  display: flex; align-items: center; justify-content: center; gap: 12px;
  padding: 80px 0; color: #888; font-size: 14px;
}
.spinner {
  width: 20px; height: 20px; border: 2px solid #333; border-top-color: #00c853;
  border-radius: 50%; animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.empty-state { text-align: center; padding: 60px; color: #666; }
.back-link { color: #00c853; text-decoration: none; }

.compare-grid { display: grid; gap: 16px; }
.compare-card {
  background: #111; border: 1px solid #1e1e1e; border-radius: 10px;
  padding: 24px; display: flex; flex-direction: column; gap: 20px;
}
.card-header { }
.card-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.12em; color: #666; }
.card-title { font-size: 14px; font-weight: 600; color: #fff; margin: 6px 0 0; line-height: 1.4; }

.card-verdict { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.verdict-label { font-size: 11px; text-transform: uppercase; color: #666; letter-spacing: 0.08em; }
.verdict-value { font-size: 18px; font-weight: 700; }
.verdict-go { color: #00b894; }
.verdict-nogo { color: #e17055; }
.verdict-caution { color: #fdcb6e; }
.confidence-badge {
  font-size: 10px; padding: 2px 8px; border-radius: 4px;
  background: rgba(255,255,255,0.06); border: 1px solid #2a2a2a;
  text-transform: capitalize; color: #999;
}

.card-section h4 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #888; margin: 0 0 8px; }
.driver-list { display: flex; flex-direction: column; gap: 4px; }
.driver-item {
  display: flex; align-items: center; gap: 8px; font-size: 12px; color: #ccc;
  padding: 4px 0;
}
.driver-name { flex: 1; }
.driver-dir { font-size: 11px; font-weight: 600; }
.dir-positive { color: #00b894; }
.dir-negative { color: #e17055; }
.dir-neutral { color: #888; }
.driver-mag { font-size: 11px; color: #666; }

.tested-list { margin: 0; padding-left: 16px; font-size: 12px; color: #999; }
.tested-list li { line-height: 1.6; }

.view-report-link {
  display: block; text-align: center; font-size: 12px; font-weight: 600;
  color: #00c853; text-decoration: none; padding: 8px;
  border: 1px solid rgba(0,200,83,0.2); border-radius: 6px; margin-top: auto;
}
.view-report-link:hover { background: rgba(0,200,83,0.08); }

@media (max-width: 768px) {
  .compare-grid { grid-template-columns: 1fr !important; }
}
</style>
