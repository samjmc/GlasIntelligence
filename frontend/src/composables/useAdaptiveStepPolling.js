import {
  step2PollMsInitial,
  step2PollMsDecay,
  graphSkipPollWhenDocumentHidden,
} from '../config/zepFootprint'

/**
 * Recursive timeout polling used in Step 2: faster interval for first ticks, then decay; optional skip when tab hidden.
 * @returns {{ start: (run: () => void | Promise<void>) => void, stop: () => void, get isActive(): boolean }}
 */
export function createAdaptiveStepPoll() {
  let active = false
  let timeoutId = null
  let ticks = 0

  function stop() {
    active = false
    if (timeoutId != null) {
      clearTimeout(timeoutId)
      timeoutId = null
    }
  }

  function schedule(run) {
    if (!active) return
    const delay = ticks >= 5 ? step2PollMsDecay : step2PollMsInitial
    timeoutId = setTimeout(async () => {
      timeoutId = null
      if (!active) return
      if (graphSkipPollWhenDocumentHidden && typeof document !== 'undefined' && document.hidden) {
        schedule(run)
        return
      }
      ticks += 1
      await run()
      if (active) schedule(run)
    }, delay)
  }

  function start(run) {
    stop()
    active = true
    ticks = 0
    schedule(run)
  }

  return {
    start,
    stop,
    get isActive() {
      return active
    },
  }
}
