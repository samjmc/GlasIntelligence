/**
 * Temporary storage for pending upload files, requirements, decision intake, and research dossier.
 * Used when user clicks start engine on home page and navigates immediately;
 * API calls are made on the Process page.
 *
 * Text fields are mirrored to sessionStorage so the state survives a page refresh
 * between Home and MainView. File objects cannot be serialized — MainView recovers
 * them from the Supabase session when the in-memory store is empty.
 */
import { reactive } from 'vue'

const STORAGE_KEY = 'glas_pending_upload'

const state = reactive({
  files: [],
  simulationRequirement: '',
  decisionIntake: null,
  researchDossier: null,
  bundleData: null,
  isPending: false
})

function _persistText() {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      simulationRequirement: state.simulationRequirement,
      decisionIntake: state.decisionIntake,
      researchDossier: state.researchDossier,
      bundleData: state.bundleData,
    }))
  } catch { /* quota */ }
}

export function setPendingUpload(files, requirement, decisionIntake = null, researchDossier = null, bundleData = null) {
  state.files = files
  state.simulationRequirement = requirement
  state.decisionIntake = decisionIntake
  state.researchDossier = researchDossier
  state.bundleData = bundleData || null
  state.isPending = true
  _persistText()
}

export function getPendingUpload() {
  if (state.isPending) {
    return {
      files: state.files,
      simulationRequirement: state.simulationRequirement,
      decisionIntake: state.decisionIntake,
      researchDossier: state.researchDossier,
      bundleData: state.bundleData,
      isPending: true
    }
  }

  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw) {
      const saved = JSON.parse(raw)
      return {
        files: [],
        simulationRequirement: saved.simulationRequirement || '',
        decisionIntake: saved.decisionIntake || null,
        researchDossier: saved.researchDossier || null,
        bundleData: saved.bundleData || null,
        isPending: true,
        recoveredFromStorage: true,
      }
    }
  } catch { /* corrupt */ }

  return {
    files: state.files,
    simulationRequirement: state.simulationRequirement,
    decisionIntake: state.decisionIntake,
    researchDossier: state.researchDossier,
    bundleData: state.bundleData,
    isPending: state.isPending
  }
}

export function clearPendingUpload() {
  state.files = []
  state.simulationRequirement = ''
  state.decisionIntake = null
  state.researchDossier = null
  state.bundleData = null
  state.isPending = false
  try { sessionStorage.removeItem(STORAGE_KEY) } catch { /* */ }
}

export default state
