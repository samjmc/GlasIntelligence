/**
 * Temporary storage for pending upload files, requirements, decision intake, and research dossier.
 * Used when user clicks start engine on home page and navigates immediately;
 * API calls are made on the Process page.
 */
import { reactive } from 'vue'

const state = reactive({
  files: [],
  simulationRequirement: '',
  decisionIntake: null,
  researchDossier: null,
  isPending: false
})

export function setPendingUpload(files, requirement, decisionIntake = null, researchDossier = null) {
  state.files = files
  state.simulationRequirement = requirement
  state.decisionIntake = decisionIntake
  state.researchDossier = researchDossier
  state.isPending = true
}

export function getPendingUpload() {
  return {
    files: state.files,
    simulationRequirement: state.simulationRequirement,
    decisionIntake: state.decisionIntake,
    researchDossier: state.researchDossier,
    isPending: state.isPending
  }
}

export function clearPendingUpload() {
  state.files = []
  state.simulationRequirement = ''
  state.decisionIntake = null
  state.researchDossier = null
  state.isPending = false
}

export default state
