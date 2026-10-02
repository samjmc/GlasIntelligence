import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// Twitter was dropped: new runs are reddit only. The run screen must start without a
// platform choice, hide the empty twitter side, and still show both sides for a run
// recorded before the drop (the static demo tapes are such runs).

const api = vi.hoisted(() => ({
  startSimulation: vi.fn(),
  stopSimulation: vi.fn(),
  getRunStatus: vi.fn(),
  getRunStatusDetail: vi.fn(),
}))
vi.mock('../api/simulation', () => api)
vi.mock('../api/report', () => ({ generateReport: vi.fn() }))
vi.mock('../lib/analytics', () => ({ trackEvent: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

import Step3Simulation from './Step3Simulation.vue'

const action = (platform, id) => ({
  id,
  platform,
  agent_id: 1,
  agent_name: 'NHSBSA',
  action_type: 'CREATE_POST',
  action_args: { content: `post ${id}` },
  round_num: 1,
  timestamp: '2026-10-02T10:00:00',
})

async function mountWith(status, actions) {
  api.startSimulation.mockResolvedValue({ success: true, data: { process_pid: 1, reddit_running: true } })
  api.getRunStatus.mockResolvedValue({ success: true, data: status })
  api.getRunStatusDetail.mockResolvedValue({ success: true, data: { all_actions: actions } })
  const wrapper = mount(Step3Simulation, {
    props: { simulationId: 'sim_x', maxRounds: 2 },
    global: { stubs: { 'router-link': true } },
  })
  await flushPromises()
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()
  return wrapper
}

describe('Step3Simulation after twitter was dropped', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('starts without a platform choice', async () => {
    const wrapper = await mountWith({ runner_status: 'running', reddit_running: true }, [])
    expect(api.startSimulation).toHaveBeenCalledTimes(1)
    expect(api.startSimulation.mock.calls[0][0]).not.toHaveProperty('platform')
    wrapper.unmount()
  })

  it('shows one platform and a single-column timeline for a reddit-only run', async () => {
    const wrapper = await mountWith(
      { runner_status: 'running', reddit_running: true, reddit_current_round: 1, reddit_actions_count: 2 },
      [action('reddit', 'a1'), action('reddit', 'a2')],
    )
    expect(wrapper.findAll('.timeline-item.reddit')).toHaveLength(2)
    expect(wrapper.find('.platform-status.twitter').exists()).toBe(false)
    expect(wrapper.find('.platform-status.reddit').exists()).toBe(true)
    expect(wrapper.find('.breakdown-item.twitter').exists()).toBe(false)
    expect(wrapper.find('.timeline-feed').classes()).toContain('single')
    wrapper.unmount()
  })

  it('still shows both sides for a run recorded before the drop', async () => {
    const wrapper = await mountWith(
      // still running: a completed status stops polling before the actions poll fires
      { runner_status: 'running', twitter_running: true, reddit_running: true, twitter_actions_count: 1 },
      [action('twitter', 't1'), action('reddit', 'r1')],
    )
    expect(wrapper.findAll('.timeline-item')).toHaveLength(2)
    expect(wrapper.find('.platform-status.twitter').exists()).toBe(true)
    expect(wrapper.find('.breakdown-item.twitter').exists()).toBe(true)
    expect(wrapper.find('.timeline-feed').classes()).not.toContain('single')
    wrapper.unmount()
  })
})
