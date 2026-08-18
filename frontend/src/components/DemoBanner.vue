<template>
  <!-- Main sticky demo banner -->
  <div v-if="visible" data-test="demo-banner" class="demo-banner">
    <span>Demo &#8212; replaying a recorded simulation</span>
    <span class="demo-banner-controls">
      <button class="demo-banner-skip" data-test="demo-skip" aria-label="Skip forward" @click="skip()">Skip &#9654;&#9654;</button>
      <button class="demo-banner-skip" data-test="demo-skip-end" aria-label="Skip to the end" @click="skipToEnd()">Skip to report &#9654;&#9654;|</button>
    </span>
    <button class="demo-banner-dismiss" data-test="banner-dismiss" aria-label="Dismiss" @click="visible = false">&times;</button>
  </div>

  <!-- Watchdog overlay: tape file failed to load (fatal — different cause from not-recorded) -->
  <div v-if="tapeFailed" data-test="watchdog-tape-failed" class="demo-watchdog-overlay demo-watchdog-tape-failed">
    <div class="demo-watchdog-box">
      <div class="demo-watchdog-icon">&#9888;</div>
      <h2 class="demo-watchdog-title">Demo tape failed to load</h2>
      <p class="demo-watchdog-body">
        The fixture file for this scenario could not be fetched (network error or missing file).
        This is a hosting or build issue — the tape file was never delivered to the browser.
      </p>
      <p class="demo-watchdog-path">Path: <code>{{ tapeFailedPath }}</code></p>
      <button class="demo-watchdog-reload" @click="reload()">Reload page</button>
    </div>
  </div>

  <!-- Watchdog overlay: call was not recorded (fixture gap — different cause from tape-load-failed) -->
  <div v-if="notRecorded" data-test="watchdog-not-recorded" class="demo-watchdog-overlay demo-watchdog-not-recorded">
    <div class="demo-watchdog-box">
      <div class="demo-watchdog-icon">&#9673;</div>
      <h2 class="demo-watchdog-title">API call not recorded in demo</h2>
      <p class="demo-watchdog-body">
        This part of the demo hit an API endpoint that was not recorded in the fixture tape.
        The simulation cannot continue from this point.
      </p>
      <p class="demo-watchdog-path">Missing path: <code>{{ notRecordedPath }}</code></p>
      <button class="demo-watchdog-reload" @click="reload()">Restart demo</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { addSkipMs, getSkipMs, loadTape } from '../demo/tape'
import { getActiveSessionId } from '../demo/adapter'
import { decodeDemoId } from '../demo/sessionId'
import { DEMO_SPEEDUP } from '../demo/config'

const visible = ref(true)
const notRecorded = ref(false)
const notRecordedPath = ref('')
const tapeFailed = ref(false)
const tapeFailedPath = ref('')

const SKIP_STEP_MS = 90_000 // 90s of tape time per click

function skip() {
  addSkipMs(SKIP_STEP_MS)
  persistSkip()
}

async function skipToEnd() {
  const scenario = decodeScenarioFromSession()
  if (!scenario) return
  try {
    const tape = await loadTape(scenario)
    // Clock: elapsed_tape_ms = (wall_base + skip) * SPEEDUP. To reach the end
    // we need skip such that (base + skip) * SPEEDUP = duration_ms.
    const id = getActiveSessionId()
    const decoded = decodeDemoId(id)
    const wallBase = decoded ? (Date.now() - decoded.startMs) : 0
    const needed = tape.duration_ms / DEMO_SPEEDUP - wallBase - getSkipMs()
    addSkipMs(Math.max(0, needed))
    persistSkip()
  } catch {
    // tape already failed loudly via the watchdog; nothing to do here
  }
}

function decodeScenarioFromSession() {
  const id = getActiveSessionId()
  if (!id) return null
  const decoded = decodeDemoId(id)
  return decoded?.scenario || null
}

// Keep skip progress across a reload so a refresh doesn't restart the walk.
function persistSkip() {
  const id = getActiveSessionId()
  if (!id) return
  try {
    sessionStorage.setItem(`demo-skip-${id}`, String(getSkipMs()))
  } catch {
    /* storage unavailable — skip persistence is best-effort */
  }
}

function restoreSkip() {
  const id = getActiveSessionId()
  if (!id) return
  try {
    const stored = sessionStorage.getItem(`demo-skip-${id}`)
    if (stored) addSkipMs(Number(stored) || 0)
  } catch {
    /* best-effort */
  }
}

function onNotRecorded(e) {
  notRecordedPath.value = e.detail?.path || ''
  notRecorded.value = true
}

function onTapeLoadFailed(e) {
  tapeFailedPath.value = e.detail?.path || ''
  tapeFailed.value = true
}

function reload() {
  window.location.reload()
}

onMounted(() => {
  window.addEventListener('demo:not-recorded', onNotRecorded)
  window.addEventListener('demo:tape-load-failed', onTapeLoadFailed)
  restoreSkip()
})

onUnmounted(() => {
  window.removeEventListener('demo:not-recorded', onNotRecorded)
  window.removeEventListener('demo:tape-load-failed', onTapeLoadFailed)
})
</script>

<style scoped>
.demo-banner {
  position: sticky;
  top: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  background: #1f2937;
  color: #e5e7eb;
}
.demo-banner-controls {
  display: flex;
  gap: 0.5rem;
}
.demo-banner-skip {
  background: #374151;
  border: 1px solid #4b5563;
  color: inherit;
  border-radius: 4px;
  padding: 0.15rem 0.6rem;
  font-size: 0.8rem;
  cursor: pointer;
}
.demo-banner-skip:hover {
  background: #4b5563;
}

.demo-banner-dismiss {
  background: none;
  border: none;
  color: inherit;
  font-size: 1.1rem;
  cursor: pointer;
}

/* Full-screen blocking overlays — prevent the user seeing a frozen spinner */
.demo-watchdog-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.85);
  color: #f3f4f6;
}

.demo-watchdog-box {
  max-width: 480px;
  padding: 2rem;
  border-radius: 12px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.demo-watchdog-tape-failed .demo-watchdog-box {
  background: #1c1917;
  border: 1px solid #78350f;
}

.demo-watchdog-not-recorded .demo-watchdog-box {
  background: #1e1b4b;
  border: 1px solid #4338ca;
}

.demo-watchdog-icon {
  font-size: 2.5rem;
}

.demo-watchdog-title {
  font-size: 1.2rem;
  font-weight: 700;
}

.demo-watchdog-body {
  font-size: 0.9rem;
  opacity: 0.85;
  line-height: 1.5;
}

.demo-watchdog-path {
  font-size: 0.8rem;
  opacity: 0.7;
  word-break: break-all;
}

.demo-watchdog-path code {
  font-family: monospace;
}

.demo-watchdog-reload {
  margin-top: 0.5rem;
  padding: 0.6rem 1.5rem;
  border: 1px solid currentColor;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 0.9rem;
}

.demo-watchdog-reload:hover {
  background: rgba(255, 255, 255, 0.1);
}
</style>
