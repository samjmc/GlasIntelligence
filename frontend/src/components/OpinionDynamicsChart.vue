<template>
  <div v-if="windows.length" class="od-card" data-test="opinion-dynamics">
    <div class="od-header">
      <h4>Opinion Over Time</h4>
      <span class="od-meta">{{ windows.length }} windows of {{ dynamics.window_rounds }} rounds · {{ dynamics.agents_judged }} agents</span>
    </div>

    <svg class="od-chart" :viewBox="`0 0 ${W} ${H}`" role="img" aria-label="Mean stance probability per window">
      <g v-for="t in TICKS" :key="'g' + t">
        <line :x1="PAD_L" :x2="W - PAD_R" :y1="y(t)" :y2="y(t)" class="od-grid" />
        <text :x="PAD_L - 6" :y="y(t) + 3" class="od-axis" text-anchor="end">{{ t * 100 }}%</text>
      </g>
      <text v-for="(w, i) in windows" :key="'x' + i" :x="x(i)" :y="H - 16" class="od-axis" text-anchor="middle">
        {{ w.label }}<tspan :x="x(i)" dy="11">n={{ w.n_agents }}</tspan>
      </text>
      <g v-for="p in POSITIONS" :key="p">
        <polyline :points="linePoints(p)" fill="none" :stroke="COLORS[p]" stroke-width="2" />
        <circle v-for="(w, i) in windows" :key="p + i" :cx="x(i)" :cy="y(prob(w, p))" r="3" :fill="COLORS[p]">
          <title>{{ w.label }} · {{ p }}: {{ pct(prob(w, p)) }}</title>
        </circle>
      </g>
    </svg>

    <div class="od-legend">
      <span v-for="p in POSITIONS" :key="p" class="od-legend-item">
        <span class="od-dot" :style="{ background: COLORS[p] }"></span>{{ p }}
      </span>
      <span class="od-uncertainty">Mean uncertainty: {{ windows.map(w => pct(w.mean_uncertainty)).join(' → ') }}</span>
    </div>

    <div class="od-movers">
      <h5>Who moved <span v-if="movers.length" class="od-meta">{{ movers.length }}</span></h5>
      <p v-if="!movers.length" class="od-none">No agent changed stance between windows.</p>
      <table v-else class="od-table">
        <thead>
          <tr><th>Agent</th><th>Stance per window</th></tr>
        </thead>
        <tbody>
          <tr v-for="m in visibleMovers" :key="m.agent">
            <td class="od-agent">{{ m.agent }}</td>
            <td class="od-path">
              <span v-for="(s, i) in m.path" :key="i" class="od-step">
                <span v-if="i" class="od-arrow">→</span>{{ s.window }}
                <span class="od-badge" :class="'stance-' + s.position">{{ s.position }}</span>
              </span>
            </td>
          </tr>
        </tbody>
      </table>
      <button
        v-if="movers.length > MOVERS_SHOWN"
        type="button"
        class="od-more"
        data-test="movers-toggle"
        @click="showAllMovers = !showAllMovers"
      >
        {{ showAllMovers ? 'Show fewer' : `Show all ${movers.length}` }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  dynamics: { type: Object, default: null },
})

// Same hues as the report's Stance Distribution bars (Step4Report.scoped.css).
const COLORS = { supportive: '#34d399', opposing: '#f87171', neutral: '#a3a3a3', ambivalent: '#fbbf24' }
const POSITIONS = ['supportive', 'opposing', 'neutral', 'ambivalent']
const TICKS = [0, 0.25, 0.5, 0.75, 1]
const W = 600
const H = 200
const PAD_L = 40
const PAD_R = 16
const PAD_T = 10
const PAD_B = 32
// A big run can move dozens of agents; keep the table short until asked.
const MOVERS_SHOWN = 10

const windows = computed(() => props.dynamics?.windows || [])
const movers = computed(() => props.dynamics?.movers || [])
const showAllMovers = ref(false)
const visibleMovers = computed(() => (showAllMovers.value ? movers.value : movers.value.slice(0, MOVERS_SHOWN)))

const x = (i) => {
  const n = windows.value.length
  return n <= 1 ? (PAD_L + W - PAD_R) / 2 : PAD_L + (i * (W - PAD_L - PAD_R)) / (n - 1)
}
const y = (v) => PAD_T + (1 - v) * (H - PAD_T - PAD_B)
const prob = (w, p) => Number(w.mean_probabilities?.[p] || 0)
const pct = (v) => `${Math.round(Number(v || 0) * 100)}%`
const linePoints = (p) => windows.value.map((w, i) => `${x(i)},${y(prob(w, p))}`).join(' ')
</script>

<style scoped>
.od-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  margin: 14px 0 24px;
}
.od-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.od-header h4 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}
.od-meta,
.od-uncertainty {
  font-size: 11px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}
.od-chart {
  width: 100%;
  height: auto;
  display: block;
}
.od-grid {
  stroke: #f3f4f6;
  stroke-width: 1;
}
.od-axis {
  font-size: 10px;
  fill: var(--text-tertiary);
  font-family: var(--font-mono);
}
.od-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: capitalize;
}
.od-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.od-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.od-uncertainty {
  margin-left: auto;
  text-transform: none;
}
.od-movers {
  margin-top: 14px;
}
.od-movers h5 {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 6px;
}
.od-movers h5 .od-meta {
  margin-left: 4px;
  font-weight: 400;
}
.od-more {
  margin-top: 6px;
  padding: 0;
  border: none;
  background: none;
  font-size: 11px;
  color: var(--text-secondary);
  text-decoration: underline;
  cursor: pointer;
}
.od-none {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0;
}
.od-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.od-table th {
  text-align: left;
  padding: 6px 8px;
  font-weight: 500;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border);
  font-size: 11px;
}
.od-table td {
  padding: 6px 8px;
  border-bottom: 1px solid #f3f4f6;
  color: var(--text-primary);
}
.od-agent {
  font-weight: 500;
}
.od-path {
  font-size: 11px;
  color: var(--text-secondary);
  font-family: var(--font-mono);
}
.od-step {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-right: 6px;
  white-space: nowrap;
}
.od-arrow {
  color: var(--text-tertiary);
}
.od-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  text-transform: capitalize;
  font-weight: 500;
}
.od-badge.stance-supportive { background: #dcfce7; color: #166534; }
.od-badge.stance-opposing { background: #fee2e2; color: #991b1b; }
.od-badge.stance-neutral { background: #f3f4f6; color: #4b5563; }
.od-badge.stance-ambivalent { background: #fef3c7; color: #92400e; }
</style>
