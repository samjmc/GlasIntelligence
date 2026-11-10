import { nextTick } from 'vue'

// When a step finishes, its next-step button may be below the fold or in a hidden
// panel. Wait for the layout to settle, then focus the button (a keyboard or screen
// reader user lands on it) and scroll it into view. Smooth scrolling is skipped when
// the user asks for reduced motion.
export async function focusNextStepButton(el) {
  await nextTick()
  if (!el || typeof el.focus !== 'function') return
  el.focus({ preventScroll: true })
  if (typeof el.scrollIntoView === 'function') {
    const reduce = typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'center' })
  }
}
