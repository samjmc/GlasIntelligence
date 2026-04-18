<template>
  <Teleport to="body">
    <div v-if="modelValue" class="rs-overlay" @click.self="close">
      <div class="rs-modal">
        <button class="rs-close" @click="close">&times;</button>

        <div class="rs-header">
          <svg class="rs-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
          <h3 class="rs-title">Research Focus</h3>
        </div>
        <p class="rs-desc">
          The AI automatically selects relevant research angles for your scenario.
          Override below to force-include or exclude specific angles.
        </p>

        <div class="rs-angles">
          <div
            v-for="angle in angles"
            :key="angle.id"
            class="rs-angle-row"
          >
            <div class="rs-angle-info">
              <span class="rs-angle-label">{{ angle.label }}</span>
              <span class="rs-angle-hint">{{ angle.hint }}</span>
            </div>
            <div class="rs-toggle-group">
              <button
                class="rs-toggle-btn"
                :class="{ active: getState(angle.id) === 'auto' }"
                @click="setState(angle.id, 'auto')"
              >Auto</button>
              <button
                class="rs-toggle-btn on"
                :class="{ active: getState(angle.id) === 'on' }"
                @click="setState(angle.id, 'on')"
              >On</button>
              <button
                class="rs-toggle-btn off"
                :class="{ active: getState(angle.id) === 'off' }"
                @click="setState(angle.id, 'off')"
              >Off</button>
            </div>
          </div>
        </div>

        <div class="rs-footer">
          <button class="rs-reset-btn" @click="resetAll">Reset All to Auto</button>
          <button class="rs-done-btn" @click="close">Done</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  angleOverrides: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:modelValue', 'update:angleOverrides'])

const angles = [
  { id: 'historical_precedents', label: 'Historical Precedents', hint: 'Similar past events and outcomes' },
  { id: 'stock_market', label: 'Stock & Financial Markets', hint: 'Share prices, revenue, analyst ratings' },
  { id: 'regulatory', label: 'Regulatory & Legal', hint: 'Laws, legislation, compliance' },
  { id: 'competitor_analysis', label: 'Competitor Analysis', hint: 'Rival strategies and positioning' },
  { id: 'public_sentiment', label: 'Public Sentiment & Media', hint: 'Press coverage, social reaction' },
  { id: 'macro_economic', label: 'Macroeconomic Context', hint: 'GDP, inflation, interest rates' },
  { id: 'industry_benchmarks', label: 'Industry Benchmarks', hint: 'Sector averages, best-in-class' },
  { id: 'geopolitical', label: 'Geopolitical Context', hint: 'International relations, sanctions' },
  { id: 'demographic', label: 'Demographic & Social Trends', hint: 'Population, workforce, behaviour' },
  { id: 'tech_landscape', label: 'Technology Landscape', hint: 'Adoption curves, disruption, patents' },
]

function getState(id) {
  if (!(id in props.angleOverrides)) return 'auto'
  return props.angleOverrides[id] ? 'on' : 'off'
}

function setState(id, state) {
  const next = { ...props.angleOverrides }
  if (state === 'auto') {
    delete next[id]
  } else {
    next[id] = state === 'on'
  }
  emit('update:angleOverrides', next)
}

function resetAll() {
  emit('update:angleOverrides', {})
}

function close() {
  emit('update:modelValue', false)
}
</script>

<style scoped>
.rs-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0, 0, 0, 0.7); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.rs-modal {
  background: var(--bg-elevated, #1a1a1a);
  border: 1px solid var(--border, #333);
  border-radius: 16px;
  padding: 32px;
  max-width: 520px;
  width: 92%;
  position: relative;
  max-height: 85vh;
  overflow-y: auto;
}
.rs-close {
  position: absolute; top: 12px; right: 16px;
  background: none; border: none; color: var(--text-secondary); font-size: 24px; cursor: pointer;
}
.rs-close:hover { color: #fff; }
.rs-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.rs-icon { color: var(--accent, #00b894); }
.rs-title { font-size: 1.15rem; font-weight: 700; color: #fff; margin: 0; }
.rs-desc {
  font-size: 0.82rem; color: var(--text-secondary, #888);
  line-height: 1.5; margin-bottom: 20px;
}

.rs-angles { display: flex; flex-direction: column; gap: 6px; }
.rs-angle-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; border-radius: 8px;
  background: var(--bg, #111); border: 1px solid var(--border, #2a2a2a);
  transition: border-color 0.15s;
}
.rs-angle-row:hover { border-color: var(--accent, #00b894); }
.rs-angle-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.rs-angle-label { font-size: 0.85rem; font-weight: 600; color: #eee; }
.rs-angle-hint { font-size: 0.72rem; color: var(--text-secondary, #666); }

.rs-toggle-group {
  display: flex; gap: 0; margin-left: 12px; flex-shrink: 0;
  border: 1px solid var(--border, #333); border-radius: 6px; overflow: hidden;
}
.rs-toggle-btn {
  padding: 4px 10px; font-size: 0.72rem; font-weight: 600;
  background: transparent; border: none; color: var(--text-secondary, #666);
  cursor: pointer; transition: all 0.15s;
  font-family: var(--font-mono, monospace);
  text-transform: uppercase; letter-spacing: 0.3px;
}
.rs-toggle-btn:not(:last-child) { border-right: 1px solid var(--border, #333); }
.rs-toggle-btn.active { color: #fff; background: rgba(255, 255, 255, 0.08); }
.rs-toggle-btn.on.active { color: var(--accent, #00b894); background: rgba(0, 184, 148, 0.12); }
.rs-toggle-btn.off.active { color: #f87171; background: rgba(248, 113, 113, 0.1); }
.rs-toggle-btn:hover:not(.active) { color: #ccc; background: rgba(255, 255, 255, 0.04); }

.rs-footer {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border, #2a2a2a);
}
.rs-reset-btn {
  background: none; border: none; color: var(--text-secondary, #666);
  font-size: 0.78rem; cursor: pointer; font-family: var(--font-mono, monospace);
  text-transform: uppercase; letter-spacing: 0.3px;
}
.rs-reset-btn:hover { color: var(--accent, #00b894); }
.rs-done-btn {
  padding: 8px 24px; border-radius: 8px; font-weight: 600; font-size: 0.85rem;
  background: var(--accent, #00b894); color: #000; border: none; cursor: pointer;
  transition: filter 0.2s;
}
.rs-done-btn:hover { filter: brightness(1.1); }
</style>
