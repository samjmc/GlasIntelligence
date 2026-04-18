<template>
  <section v-if="synthesis" class="bundle-synthesis" aria-label="Executive synthesis">
    <header class="synth-header">
      <h2 class="synth-title">Executive synthesis</h2>
      <span v-if="synthesis.llm_assigned_weights" class="synth-badge" title="Branch weights were suggested by the model">
        Model weights
      </span>
      <span v-else class="synth-badge user" title="Weights adjusted manually">
        Your weights
      </span>
      <span v-if="isSaving" class="synth-saving">Saving…</span>
    </header>

    <div v-if="synthesis.narrative_md" class="synth-narrative">
      <p v-for="(para, i) in narrativeParagraphs" :key="i" class="synth-para">{{ para }}</p>
    </div>

    <div v-if="localWeights.length" class="synth-weights">
      <h3 class="synth-sub">Branch weights</h3>
      <p class="synth-hint">Adjust how likely each scenario is as the true branch. Marginals update below.</p>
      <p v-if="saveError" class="synth-save-error" role="alert">{{ saveError }}</p>
      <div v-for="b in localWeights" :key="b.scenario_index" class="weight-row">
        <div class="weight-label">
          <span class="weight-idx">{{ b.scenario_index + 1 }}</span>
          <span class="weight-title">{{ scenarioTitle(b.scenario_index) }}</span>
        </div>
        <input
          type="range"
          class="weight-slider"
          min="5"
          max="85"
          :step="1"
          :value="Math.round(b.p_branch * 100)"
          @input="onSliderInput(b.scenario_index, $event.target.value)"
        />
        <span class="weight-pct">{{ (b.p_branch * 100).toFixed(1) }}%</span>
      </div>
    </div>

    <div v-if="previewOutcomes.length" class="synth-outcomes">
      <h3 class="synth-sub">Synthesized outcome marginals</h3>
      <table class="synth-table">
        <thead>
          <tr>
            <th>Outcome</th>
            <th>Mid %</th>
            <th>Approx. 95% range</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in previewOutcomes" :key="row.outcome_id">
            <td>{{ row.label }}</td>
            <td>{{ row.displayMid != null ? row.displayMid.toFixed(1) : '—' }}</td>
            <td>
              <span v-if="row.lo != null && row.hi != null">
                {{ row.lo.toFixed(0) }} – {{ row.hi.toFixed(0) }}
              </span>
              <span v-else>—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="synthesis.robust_conclusions?.length" class="synth-list-block">
      <h3 class="synth-sub">Robust across branches</h3>
      <ul>
        <li v-for="(line, i) in synthesis.robust_conclusions" :key="'r' + i">{{ line }}</li>
      </ul>
    </div>

    <div v-if="synthesis.contingent_conclusions?.length" class="synth-list-block muted">
      <h3 class="synth-sub">Contingent on branch</h3>
      <ul>
        <li v-for="(line, i) in synthesis.contingent_conclusions" :key="'c' + i">{{ line }}</li>
      </ul>
    </div>

    <div v-if="synthesis.decision_matrix?.length" class="synth-matrix">
      <h3 class="synth-sub">Per-scenario decision read</h3>
      <div
        v-for="row in synthesis.decision_matrix"
        :key="'dm' + row.scenario_index"
        class="matrix-row"
      >
        <div class="matrix-head">
          <span class="weight-idx">{{ (row.scenario_index ?? 0) + 1 }}</span>
          <span class="matrix-verdict">{{ row.verdict || '—' }}</span>
          <span v-if="row.confidence" class="matrix-conf">{{ row.confidence }}</span>
        </div>
        <p v-if="row.key_drivers_summary" class="matrix-drivers">{{ row.key_drivers_summary }}</p>
      </div>
    </div>

    <div v-if="synthesis.early_warnings?.length" class="synth-warnings">
      <h3 class="synth-sub">Early warnings</h3>
      <div v-for="(w, i) in synthesis.early_warnings" :key="'w' + i" class="warn-card">
        <div class="warn-ind">{{ w.indicator || 'Signal' }}</div>
        <div class="warn-mean">{{ w.signal_meaning }}</div>
        <div v-if="w.source" class="warn-src">{{ w.source }}</div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { patchBundleSynthesisWeights } from '../api/simulation'

const props = defineProps({
  bundleId: { type: String, required: true },
  synthesis: { type: Object, default: null },
  scenarios: { type: Array, default: () => [] },
})

const emit = defineEmits(['updated'])

const localWeights = ref([])
const isSaving = ref(false)
const saveError = ref('')
/** JSON snapshot of branch weights last persisted successfully; null until first successful save. */
const lastSavedWeights = ref(null)
/** Count of auto re-queues from `finally` when weights drift; capped to avoid infinite retry on API failure. */
const saveRetryCount = ref(0)
const SAVE_FINALLY_RETRY_LIMIT = 3
let debounceTimer = null

function serializeWeights(weights) {
  if (!weights?.length) return '[]'
  return JSON.stringify(
    [...weights]
      .map((b) => ({ scenario_index: b.scenario_index, p_branch: b.p_branch }))
      .sort((a, b) => a.scenario_index - b.scenario_index),
  )
}

watch(
  () => props.synthesis,
  (s) => {
    if (!s?.branch_weights?.length) {
      localWeights.value = []
      return
    }
    localWeights.value = s.branch_weights.map((b) => ({
      scenario_index: b.scenario_index,
      p_branch: Number(b.p_branch),
      rationale: b.rationale || '',
    }))
  },
  { immediate: true },
)

const narrativeParagraphs = computed(() => {
  const md = props.synthesis?.narrative_md
  if (!md || typeof md !== 'string') return []
  return md
    .split(/\n\n+/)
    .map((p) => p.trim())
    .filter(Boolean)
})

const weightMap = computed(() =>
  Object.fromEntries(localWeights.value.map((b) => [b.scenario_index, b.p_branch])),
)

/** Match server: renormalize weights over branches present in each outcome's mapping. */
const previewOutcomes = computed(() => {
  const rd = props.synthesis?.recalc_data || []
  const wm = weightMap.value
  const outs = props.synthesis?.outcomes || []
  return rd.map((row) => {
    const parts = row.per_branch || []
    let sw = 0
    let sp = 0
    for (const pb of parts) {
      const w = wm[pb.scenario_index] ?? 0
      sw += w
      sp += w * (pb.mean_0_1 ?? 0)
    }
    const mid = sw > 0 ? (sp / sw) * 100 : null
    const full = outs.find((o) => o.outcome_id === row.outcome_id)
    const label = full?.label || row.outcome_id
    return {
      outcome_id: row.outcome_id,
      label,
      displayMid: mid,
      lo: full?.marginal_ci_low_percent ?? null,
      hi: full?.marginal_ci_high_percent ?? null,
    }
  })
})

function scenarioTitle(idx) {
  const sc = props.scenarios.find((x) => x.scenario_index === idx)
  return sc?.title || `Scenario ${idx + 1}`
}

function onSliderInput(scenarioIndex, rawVal) {
  const pct = Math.max(5, Math.min(85, Number(rawVal)))
  const b = localWeights.value.find((x) => x.scenario_index === scenarioIndex)
  if (b) b.p_branch = pct / 100
  const s = localWeights.value.reduce((a, x) => a + x.p_branch, 0)
  if (s > 0) {
    localWeights.value.forEach((x) => {
      x.p_branch = x.p_branch / s
    })
  }
  scheduleSave()
}

function scheduleSave() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(saveWeights, 550)
}

async function saveWeights() {
  if (!props.bundleId || !localWeights.value.length) return
  if (isSaving.value) return
  const snapshot = localWeights.value.map((b) => ({ ...b }))
  isSaving.value = true
  try {
    const res = await patchBundleSynthesisWeights(props.bundleId, {
      branch_weights: localWeights.value.map((b) => ({
        scenario_index: b.scenario_index,
        p_branch: b.p_branch,
      })),
    })
    if (res?.data) {
      saveError.value = ''
      emit('updated', res.data)
      lastSavedWeights.value = serializeWeights(localWeights.value)
      saveRetryCount.value = 0
    }
  } catch (e) {
    localWeights.value = snapshot.map((w) => ({ ...w }))
    saveError.value = 'Failed to save weights — please try again'
    console.error('patchBundleSynthesisWeights', e)
  } finally {
    isSaving.value = false
    if (
      serializeWeights(localWeights.value) !== lastSavedWeights.value &&
      saveRetryCount.value < SAVE_FINALLY_RETRY_LIMIT
    ) {
      saveRetryCount.value += 1
      scheduleSave()
    }
  }
}
</script>

<style scoped>
.bundle-synthesis {
  margin-bottom: 32px;
  padding: 24px;
  background: var(--bg-secondary, #111118);
  border: 1px solid var(--border, rgba(255, 255, 255, 0.08));
  border-radius: 12px;
}
.synth-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.synth-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}
.synth-badge {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(0, 200, 83, 0.15);
  color: var(--accent, #00c853);
}
.synth-badge.user {
  background: rgba(100, 180, 255, 0.12);
  color: #90caf9;
}
.synth-saving {
  font-size: 12px;
  color: var(--text-secondary, #888);
  margin-left: auto;
}
.synth-narrative {
  margin-bottom: 20px;
}
.synth-para {
  margin: 0 0 12px;
  font-size: 14px;
  line-height: 1.55;
  color: var(--text-primary, #e8e8ed);
}
.synth-sub {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #e8e8ed);
}
.synth-hint {
  margin: 0 0 14px;
  font-size: 12px;
  color: var(--text-secondary, #888);
}
.synth-save-error {
  margin: 0 0 14px;
  font-size: 12px;
  color: #ef5350;
}
.synth-weights {
  margin-bottom: 24px;
}
.weight-row {
  display: grid;
  grid-template-columns: 1fr minmax(120px, 1fr) 52px;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}
.weight-label {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.weight-idx {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.06);
}
.weight-title {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.weight-slider {
  width: 100%;
  accent-color: var(--accent, #00c853);
}
.weight-pct {
  font-size: 12px;
  font-family: var(--font-mono, monospace);
  text-align: right;
  color: var(--text-secondary);
}
.synth-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.synth-table th,
.synth-table td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border, rgba(255, 255, 255, 0.06));
}
.synth-table th {
  color: var(--text-secondary);
  font-weight: 500;
}
.synth-list-block {
  margin-top: 20px;
}
.synth-list-block.muted ul {
  opacity: 0.9;
}
.synth-list-block ul {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-primary, #ddd);
}
.synth-matrix {
  margin-top: 20px;
}
.matrix-row {
  padding: 12px 0;
  border-bottom: 1px solid var(--border, rgba(255, 255, 255, 0.06));
}
.matrix-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.matrix-verdict {
  font-weight: 600;
  font-size: 13px;
}
.matrix-conf {
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: uppercase;
}
.matrix-drivers {
  margin: 8px 0 0 30px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.45;
}
.synth-warnings {
  margin-top: 20px;
}
.warn-card {
  padding: 10px 12px;
  margin-bottom: 8px;
  border-radius: 8px;
  background: rgba(255, 152, 0, 0.08);
  border: 1px solid rgba(255, 152, 0, 0.2);
}
.warn-ind {
  font-size: 12px;
  font-weight: 600;
  color: #ffb74d;
}
.warn-mean {
  font-size: 13px;
  margin-top: 4px;
}
.warn-src {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 4px;
}
</style>
