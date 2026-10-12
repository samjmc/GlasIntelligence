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
const apiPost = vi.hoisted(() => vi.fn())
// What GET /billing/<path> answers; tests replace it to play a free-plan user
const billing = vi.hoisted(() => ({ status: { plan: 'pro' }, canSimulate: { plan: 'pro', can_simulate: true } }))

vi.mock('../api/simulation', () => api)
vi.mock('../store/pendingUpload', () => pending)
vi.mock('../composables/useApi', () => ({
  useApi: () => ({
    apiGet: vi.fn(async (path) => ({
      success: true,
      data: path === '/billing/can-simulate' ? billing.canSimulate : billing.status,
    })),
    apiPost,
  }),
}))
vi.mock('../lib/analytics', () => ({ trackEvent: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }), useRoute: () => ({ query: {} }) }))

import Home from './Home.vue'

function mountHome() {
  return mount(Home, {
    global: {
      stubs: { AppNavbar: true, HistoryDatabase: true, DemoScenarioPicker: true, teleport: true, RouterLink: true },
    },
  })
}

function freeUser(freeRunLeft) {
  billing.status = { plan: 'free' }
  billing.canSimulate = {
    plan: 'free', can_simulate: freeRunLeft, free_run_left: freeRunLeft, free_agents: 25, free_rounds: 15,
  }
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

  // Live 2026-10-12: an Enterprise user with 0 research credits got 402 and the page said
  // "Failed to connect to the server", so starting without a document was impossible.
  it('with no research credits left, writes a quick briefing instead and starts', async () => {
    const err = Object.assign(new Error('Request failed with status code 402'), {
      response: { status: 402, data: { error: 'no_research_credits', message: 'No research credits remaining.' } },
    })
    api.startDeepResearch.mockRejectedValue(err)
    apiPost.mockResolvedValue({
      success: true,
      data: { title: 'Research Briefing', content_md: '# Quick', filename: 'briefing_x.md' },
    })

    const wrapper = mountHome()
    await flushPromises()
    await wrapper.find('textarea.code-input').setValue('What if the US raises steel tariffs?')
    await wrapper.find('[data-test="start-btn"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/source/auto-research', { prompt: 'What if the US raises steel tariffs?' })
    const [files] = pending.setPendingUpload.mock.calls[0]
    expect(files.map((f) => f.name)).toEqual(['briefing_x.md'])
    expect(push).toHaveBeenCalledWith({ name: 'Process', params: { projectId: 'new' } })
    wrapper.unmount()
  })
})

describe('Home for a free-plan user', () => {
  afterEach(() => {
    billing.status = { plan: 'pro' }
    billing.canSimulate = { plan: 'pro', can_simulate: true }
    vi.clearAllMocks()
  })

  it('with the free run left: shows the note and starts like a paid user (no upgrade modal)', async () => {
    freeUser(true)
    api.startDeepResearch.mockResolvedValue({ success: false, error: 'stop here' })

    const wrapper = mountHome()
    await flushPromises()
    expect(wrapper.find('[data-test="free-plan-note"]').text()).toBe(
      'Free plan: 1 simulation this month (up to 25 agents, 15 rounds).',
    )

    await wrapper.find('textarea.code-input').setValue('What if the US raises steel tariffs?')
    expect(wrapper.find('[data-test="research-first-hint"]').exists()).toBe(true)
    await wrapper.find('[data-test="start-btn"]').trigger('click')
    await flushPromises()

    expect(api.startDeepResearch).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.upgrade-modal').exists()).toBe(false)
    wrapper.unmount()
  })

  it('with the free run used: says so and shows the upgrade modal on start', async () => {
    freeUser(false)

    const wrapper = mountHome()
    await flushPromises()
    expect(wrapper.find('[data-test="free-plan-note"]').text()).toContain(
      'Free plan: your free simulation for this month is used.',
    )

    await wrapper.find('textarea.code-input').setValue('What if the US raises steel tariffs?')
    await wrapper.find('[data-test="start-btn"]').trigger('click')
    await flushPromises()

    expect(api.startDeepResearch).not.toHaveBeenCalled()
    expect(wrapper.find('.upgrade-modal').exists()).toBe(true)
    wrapper.unmount()
  })

  it('with no free briefings left: asks for a document, no paid-only quick briefing', async () => {
    freeUser(true)
    api.startDeepResearch.mockRejectedValue(
      Object.assign(new Error('Request failed with status code 402'), {
        response: { status: 402, data: { error: 'no_research_credits', message: 'No research credits remaining.' } },
      }),
    )

    const wrapper = mountHome()
    await flushPromises()
    await wrapper.find('textarea.code-input').setValue('What if the US raises steel tariffs?')
    await wrapper.find('[data-test="start-btn"]').trigger('click')
    await flushPromises()

    expect(apiPost).not.toHaveBeenCalledWith('/source/auto-research', expect.anything())
    expect(push).not.toHaveBeenCalled()
    expect(wrapper.find('.research-error').text()).toBe(
      'No free research briefings left this month. Upload a document to start.',
    )
    wrapper.unmount()
  })

  it('shows no free-plan note to a paid user', async () => {
    const wrapper = mountHome()
    await flushPromises()
    expect(wrapper.find('[data-test="free-plan-note"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
