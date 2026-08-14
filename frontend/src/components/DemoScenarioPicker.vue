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
        :data-scenario-id="s.id"
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
import { SCHEMA_VERSION } from '../demo/tape'

const scenarios = ref([])
const error = ref(false)

const emit = defineEmits(['select'])

async function fetchManifest() {
  // One retry: same policy as tape.js loadTape() — a CDN hiccup on a static
  // asset is usually transient. A second failure is real and must surface.
  let res
  try {
    res = await fetch('/demo/manifest.json')
    if (!res.ok) throw new Error(`manifest ${res.status}`)
  } catch {
    res = await fetch('/demo/manifest.json')
    if (!res.ok) throw new Error(`manifest ${res.status}`)
  }
  const manifest = await res.json()
  if (manifest.schema_version !== SCHEMA_VERSION) {
    throw new Error(
      `Demo manifest schema ${manifest.schema_version} does not match expected ${SCHEMA_VERSION}`,
    )
  }
  return manifest
}

onMounted(async () => {
  try {
    const manifest = await fetchManifest()
    scenarios.value = manifest.scenarios
  } catch (e) {
    error.value = e?.message || 'Demo failed to load. Please reload the page.'
  }
})

function choose(scenario) {
  // The session id is intentionally NOT minted here. Minting at picker-click
  // and then navigating to start the run a few seconds later burns virtual-clock
  // time between click and run-start — at 20× speedup a 5 s gap loses 100 s
  // of tape. Home.vue's startSimulation() mints the id at the moment the run
  // actually begins. The picker's only job is selecting a scenario.
  emit('select', { scenarioId: scenario.id, prompt: scenario.prompt })
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
