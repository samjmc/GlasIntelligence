<template>
  <div class="demo-picker">
    <h2 class="demo-picker-title">Choose a worked example</h2>

    <p v-if="error" data-test="picker-error" class="demo-picker-error">
      {{ typeof error === 'string' ? error : 'Demo failed to load. Please reload the page.' }}
    </p>

    <div v-else class="demo-picker-grid">
      <button
        v-for="s in scenarios"
        :key="s.id"
        data-test="scenario-card"
        class="demo-picker-card"
        @click="choose(s)"
      >
        <span class="demo-picker-card-title">{{ s.title }}</span>
        <span class="demo-picker-card-blurb">{{ s.blurb }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { encodeDemoId } from '../demo/sessionId'
import { setActiveScenario } from '../demo/adapter'

const scenarios = ref([])
const error = ref(false)

const emit = defineEmits(['select'])

onMounted(async () => {
  try {
    const res = await fetch('/demo/manifest.json')
    if (!res.ok) throw new Error(`manifest ${res.status}`)
    scenarios.value = (await res.json()).scenarios
  } catch {
    error.value = true
  }
})

function choose(scenario) {
  let sessionId
  try {
    sessionId = encodeDemoId(Date.now(), scenario.id)
  } catch (e) {
    error.value = `Cannot start scenario "${scenario.id}": ${e.message}`
    return
  }
  setActiveScenario(scenario.id, sessionId)
  emit('select', { scenarioId: scenario.id, sessionId, prompt: scenario.prompt })
}
</script>

<style scoped>
.demo-picker {
  margin-bottom: 1.5rem;
}
.demo-picker-title {
  font-size: 1.1rem;
  font-weight: 600;
  margin-bottom: 1rem;
}
.demo-picker-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1rem;
}
.demo-picker-card {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1.25rem;
  text-align: left;
  cursor: pointer;
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  background: transparent;
  color: inherit;
}
.demo-picker-card:hover {
  border-color: var(--accent-color, #6ee7b7);
}
.demo-picker-card-title {
  font-weight: 600;
}
.demo-picker-card-blurb {
  opacity: 0.75;
  font-size: 0.9rem;
}
.demo-picker-error {
  color: #ef4444;
  padding: 0.75rem;
  border: 1px solid #ef4444;
  border-radius: 6px;
}
</style>
