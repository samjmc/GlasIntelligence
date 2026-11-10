import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

// When the graph build finishes, the "Proceed to Environment Setup" button used to sit
// below the fold with nothing telling the user. It must be announced, focused and a
// native button.

vi.mock('../api/simulation', () => ({ createSimulation: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

import Step1GraphBuild from './Step1GraphBuild.vue'

const projectData = {
  project_id: 'p1',
  graph_id: 'g1',
  ontology: { entity_types: [{ name: 'Pharmacy' }], edge_types: [{ name: 'SUPPLIES' }] },
}

const mountStep = (currentPhase) => mount(Step1GraphBuild, {
  props: { currentPhase, projectData },
  attachTo: document.body,
})

describe('Step1GraphBuild when the build completes', () => {
  afterEach(() => { document.body.innerHTML = '' })

  it('announces the finished step, asks the page to show the panel, and focuses the next button', async () => {
    const wrapper = mountStep(1)
    const live = wrapper.find('[data-test="step-ready-message"]')
    expect(live.attributes('aria-live')).toBe('polite')
    expect(live.text()).toBe('')

    await wrapper.setProps({ currentPhase: 2 })
    await nextTick()
    await nextTick()

    expect(live.text()).toBe('Graph built. Next: environment setup.')
    expect(wrapper.emitted('step-ready')).toHaveLength(1)
    const btn = wrapper.find('[data-test="proceed-env-setup"]')
    expect(btn.element.tagName).toBe('BUTTON')
    expect(btn.attributes('type')).toBe('button')
    expect(document.activeElement).toBe(btn.element)
    wrapper.unmount()
  })

  it('does not steal focus when the panel opens on an already finished build', async () => {
    const wrapper = mountStep(2)
    await nextTick()
    expect(wrapper.emitted('step-ready')).toBeUndefined()
    expect(document.activeElement).not.toBe(wrapper.find('[data-test="proceed-env-setup"]').element)
    wrapper.unmount()
  })

  it('renders the ontology tags as real buttons the keyboard can reach', () => {
    const wrapper = mountStep(2)
    const tags = wrapper.findAll('.entity-tag')
    expect(tags).toHaveLength(2)
    for (const tag of tags) {
      expect(tag.element.tagName).toBe('BUTTON')
      expect(tag.attributes('type')).toBe('button')
    }
    wrapper.unmount()
  })
})
