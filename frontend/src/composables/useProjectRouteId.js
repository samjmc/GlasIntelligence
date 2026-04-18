import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

/** Keeps a ref in sync with `route.params.projectId` (e.g. Process view). */
export function useProjectRouteId() {
  const route = useRoute()
  const projectId = ref(route.params.projectId)
  watch(
    () => route.params.projectId,
    (v) => {
      projectId.value = v
    }
  )
  return { route, projectId }
}
