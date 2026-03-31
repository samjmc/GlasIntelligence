<template>
  <div class="bundle-progress" v-if="bundle">
    <div class="bundle-header">
      <div class="bundle-label">Decision Analysis</div>
      <h3 class="bundle-title">{{ bundle.title }}</h3>
      <div class="bundle-stats">
        <span class="bundle-count">{{ bundle.progress?.completed || 0 }} of {{ bundle.progress?.total || 0 }} scenarios tested</span>
        <span class="bundle-status" :class="'status-' + bundle.status">{{ bundle.status === 'completed' ? 'Complete' : 'In Progress' }}</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPct + '%' }"></div>
      </div>
    </div>

    <div class="scenario-list">
      <div
        v-for="(scenario, idx) in (bundle.suggested_scenarios || [])"
        :key="idx"
        class="scenario-item"
        :class="{ completed: isCompleted(idx), current: isCurrent(idx) }"
      >
        <div class="scenario-marker">
          <svg v-if="isCompleted(idx)" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#00c853" stroke-width="3">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          <span v-else class="scenario-index">{{ idx + 1 }}</span>
        </div>
        <div class="scenario-info">
          <span class="scenario-title">{{ scenario.title }}</span>
          <span class="scenario-change">{{ scenario.change_summary }}</span>
        </div>
        <div class="scenario-action">
          <router-link
            v-if="isCompleted(idx) && getReportId(idx)"
            :to="'/report/' + getReportId(idx)"
            class="scenario-link"
          >View Report</router-link>
          <button
            v-else-if="!isCompleted(idx)"
            class="scenario-run-btn"
            @click="$emit('run-scenario', scenario, idx)"
          >Run This</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  bundle: { type: Object, required: true },
})

defineEmits(['run-scenario'])

const completedIndices = computed(() => {
  const completed = props.bundle?.completed_scenarios || []
  return new Set(completed.map(c => c.scenario_index))
})

const progressPct = computed(() => {
  const total = props.bundle?.progress?.total || 1
  const completed = props.bundle?.progress?.completed || 0
  return Math.round((completed / total) * 100)
})

const isCompleted = (idx) => completedIndices.value.has(idx)
const isCurrent = (idx) => !isCompleted(idx) && idx === nextPendingIndex.value

const nextPendingIndex = computed(() => {
  const total = props.bundle?.suggested_scenarios?.length || 0
  for (let i = 0; i < total; i++) {
    if (!completedIndices.value.has(i)) return i
  }
  return -1
})

const getReportId = (idx) => {
  const completed = props.bundle?.completed_scenarios || []
  const match = completed.find(c => c.scenario_index === idx)
  return match?.report_id || ''
}
</script>

<style scoped>
.bundle-progress {
  background: #111;
  border: 1px solid #1e1e1e;
  border-radius: 10px;
  padding: 24px;
}
.bundle-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #00c853;
  margin-bottom: 6px;
}
.bundle-title {
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  margin: 0 0 10px;
}
.bundle-stats {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.bundle-count {
  font-size: 13px;
  color: #999;
}
.bundle-status {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 2px 8px;
  border-radius: 4px;
}
.status-in_progress {
  background: rgba(33, 150, 243, 0.12);
  color: #42a5f5;
}
.status-completed {
  background: rgba(0, 200, 83, 0.12);
  color: #00c853;
}
.progress-bar {
  width: 100%;
  height: 4px;
  background: #1a1a1a;
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 20px;
}
.progress-fill {
  height: 100%;
  background: #00c853;
  border-radius: 2px;
  transition: width 0.4s ease;
}
.scenario-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.scenario-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid #1e1e1e;
  transition: border-color 0.2s;
}
.scenario-item.current {
  border-color: #00c853;
  background: rgba(0, 200, 83, 0.04);
}
.scenario-item.completed {
  opacity: 0.7;
}
.scenario-marker {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.scenario-index {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 1px solid #333;
}
.scenario-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.scenario-title {
  font-size: 13px;
  font-weight: 500;
  color: #e0e0e0;
}
.scenario-change {
  font-size: 11px;
  color: #666;
}
.scenario-link {
  font-size: 11px;
  color: #42a5f5;
  text-decoration: none;
}
.scenario-link:hover {
  text-decoration: underline;
}
.scenario-run-btn {
  font-size: 11px;
  font-weight: 600;
  color: #00c853;
  background: transparent;
  border: 1px solid rgba(0, 200, 83, 0.3);
  border-radius: 4px;
  padding: 4px 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.scenario-run-btn:hover {
  background: #00c853;
  color: #000;
}
</style>
