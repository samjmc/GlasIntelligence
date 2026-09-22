import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import OpinionDynamicsChart from './OpinionDynamicsChart.vue'

const probs = (opposing, supportive) => ({ opposing, supportive, neutral: 0.05, ambivalent: 1 - opposing - supportive - 0.05 })

const DYNAMICS = {
  window_rounds: 4,
  positions: ['supportive', 'opposing', 'neutral', 'ambivalent'],
  agents_judged: 3,
  windows: [
    { label: 'R1-4', n_agents: 3, mean_probabilities: probs(0.87, 0.05), mean_uncertainty: 0.12, agents: [] },
    { label: 'R5-8', n_agents: 3, mean_probabilities: probs(0.6, 0.2), mean_uncertainty: 0.3, agents: [] },
  ],
  movers: [
    {
      agent: 'NHSBSA',
      from: 'opposing',
      to: 'neutral',
      path: [
        { window: 'R1-4', position: 'opposing' },
        { window: 'R5-8', position: 'neutral' },
      ],
    },
  ],
}

describe('OpinionDynamicsChart', () => {
  it('draws one line per position across the windows, and the movers table', () => {
    const w = mount(OpinionDynamicsChart, { props: { dynamics: DYNAMICS } })
    expect(w.find('[data-testid="opinion-dynamics"]').exists()).toBe(true)

    const lines = w.findAll('polyline')
    expect(lines).toHaveLength(4)
    lines.forEach((l) => expect(l.attributes('points').split(' ')).toHaveLength(2))
    expect(w.findAll('circle')).toHaveLength(8)
    expect(w.text()).toContain('R1-4')
    expect(w.text()).toContain('R5-8')
    expect(w.text()).toContain('12% → 30%')

    const rows = w.findAll('tbody tr')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('NHSBSA')
    expect(rows[0].text()).toContain('R1-4 opposing → R5-8 neutral')
  })

  it('says so when nobody moved', () => {
    const w = mount(OpinionDynamicsChart, { props: { dynamics: { ...DYNAMICS, movers: [] } } })
    expect(w.find('table').exists()).toBe(false)
    expect(w.text()).toContain('No agent changed stance')
  })

  it.each([
    ['no prop', {}],
    ['null', { dynamics: null }],
    ['no windows', { dynamics: { ...DYNAMICS, windows: [] } }],
  ])('renders nothing with %s', (_name, props) => {
    const w = mount(OpinionDynamicsChart, { props })
    expect(w.find('[data-testid="opinion-dynamics"]').exists()).toBe(false)
    expect(w.find('svg').exists()).toBe(false)
    expect(w.text()).toBe('')
  })
})
