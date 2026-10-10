import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// Starting with no documents used to dead-end on /process/new ("No pending files
// found"). The start button must always be visible, and a paid user with no files
// must get a research briefing written first.

const api = vi.hoisted(() => ({
  startDeepResearch: vi.fn(),
  getDeepResearchStatus: vi.fn(),
  getDeepResearchResult: vi.fn(),
  createBundle: vi.fn(),
}))
const pending = vi.hoisted(() => ({
  setPendingUpload: vi.fn(),
  getPendingUpload: vi.fn(() => ({})),
  clearPendingUpload: vi.fn(),
}))
const push = vi.hoisted(() => vi.fn())

vi.mock('../api/simulation', () => api)
vi.mock('../store/pendingUpload', () => pending)
vi.mock('../composables/useApi', () => ({
  useApi: () => ({
    apiGet: vi.fn(async () => ({ success: true, data: { plan: 'pro' } })),
    apiPost: vi.fn(),
  }),
}))
vi.mock('../lib/analytics', () => ({ trackEvent: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }), useRoute: () => ({ query: {} }) }))

import Home from './Home.vue'

function mountHome() {
  return mount(Home, {
    global: { stubs: { AppNavbar: true, HistoryDatabase: true, DemoScenarioPicker: true, teleport: true } },
  })
}

describe('Home start flow', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('shows the start button before any text is typed, disabled until there is a scenario', async () => {
    const wrapper = mountHome()
    await flushPromises()

    const btn = wrapper.find('[data-test="start-btn"]')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toContain('Start simulation')
    expect(btn.attributes('disabled')).toBeDefined()

    await wrapper.find('textarea.code-input').setValue('What if the US raises steel tariffs?')
    expect(wrapper.find('[data-test="start-btn"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('shows the research-first hint to a paid user with no documents', async () => {
    const wrapper = mountHome()
    await flushPromises()
    expect(wrapper.find('[data-test="research-first-hint"]').text()).toContain('No documents?')
    wrapper.unmount()
  })

  it('writes a research briefing first when no files are attached, then starts', async () => {
    api.startDeepResearch.mockResolvedValue({ success: true, data: { task_id: 't1' } })
    api.getDeepResearchStatus.mockResolvedValue({ success: true, data: { status: 'completed' } })
    api.getDeepResearchResult.mockResolvedValue({ success: true, data: { summary_md: '# Briefing' } })

    const wrapper = mountHome()
    await flushPromises()
    await wrapper.find('textarea.code-input').setValue('What if the US raises steel tariffs?')
    await wrapper.find('[data-test="start-btn"]').trigger('click')
    await flushPromises()
    expect(api.startDeepResearch).toHaveBeenCalledTimes(1)
    expect(push).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(4000)
    await flushPromises()

    expect(pending.setPendingUpload).toHaveBeenCalledTimes(1)
    const [files, scenario] = pending.setPendingUpload.mock.calls[0]
    expect(files.map((f) => f.name)).toEqual(['deep_research_dossier.md'])
    expect(scenario).toBe('What if the US raises steel tariffs?')
    expect(push).toHaveBeenCalledWith({ name: 'Process', params: { projectId: 'new' } })
    wrapper.unmount()
  })

  it('stops (and shows the error) when the research briefing fails', async () => {
    api.startDeepResearch.mockRejectedValue(new Error('boom'))

    const wrapper = mountHome()
    await flushPromises()
    await wrapper.find('textarea.code-input').setValue('What if the US raises steel tariffs?')
    await wrapper.find('[data-test="start-btn"]').trigger('click')
    await flushPromises()

    expect(api.startDeepResearch).toHaveBeenCalledTimes(1)
    expect(pending.setPendingUpload).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
    expect(wrapper.find('.research-error').text()).toBe('Failed to connect to the server')
    wrapper.unmount()
  })
})
