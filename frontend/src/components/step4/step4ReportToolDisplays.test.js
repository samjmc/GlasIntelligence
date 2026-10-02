import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { parseInterview, parsePanorama } from './step4ReportParsers.js'
import { InterviewDisplay, PanoramaDisplay } from './step4ReportToolDisplays.js'
import generated from './__fixtures__/generatedToolResults.json'

// Renders the Step 4 tool panels from real recorded results. Before the parser fix the
// interview panel had no agents and no answers; the panels also printed mojibake symbols.

const MOJIBAKE = /Ã|Â|â[\u0080-⃿]|ã€|ï¼|é[\u0080-⃿]|å[\u0080-⃿]/

const recorded = (scenario, tool) => {
  const tape = JSON.parse(readFileSync(resolve(process.cwd(), 'public', 'demo', scenario, 'tape.json'), 'utf8'))
  const out = []
  const walk = (o) => {
    if (Array.isArray(o)) return o.forEach(walk)
    if (!o || typeof o !== 'object') return
    if (o.details && o.details.tool_name === tool && typeof o.details.result === 'string') out.push(o.details.result)
    Object.values(o).forEach(walk)
  }
  walk(tape)
  return out.sort((a, b) => b.length - a.length)[0]
}

describe('InterviewDisplay', () => {
  it('shows every interviewed agent and splits each answer per question', () => {
    const w = mount(InterviewDisplay, {
      props: { result: parseInterview(recorded('energy-price-cap', 'interview_agents')), resultLength: 58379 },
    })
    expect(w.findAll('.agent-tab')).toHaveLength(6)
    expect(w.find('.profile-name').text()).toBe('energy_retail_companies_255')
    expect(w.findAll('.qa-pair')).toHaveLength(5)
    const firstAnswer = w.find('.qa-answer').text()
    expect(firstAnswer).toMatch(/January 2027 cap of £1,840/)
    expect(firstAnswer).not.toMatch(/Question 2:/)
    // a run from before twitter was dropped answered on both platforms
    expect(w.find('.platform-switch').exists()).toBe(true)
    expect(w.text()).toContain('·')
    expect(w.html()).not.toMatch(MOJIBAKE)
  })

  it('shows a reddit-only answer without a platform switch', () => {
    const w = mount(InterviewDisplay, { props: { result: parseInterview(generated.interview_reddit_only) } })
    expect(w.findAll('.agent-tab')).toHaveLength(2)
    expect(w.find('.qa-answer').text()).toMatch(/Payments are calculated only for consultations up to the cap/)
    expect(w.find('.platform-switch').exists()).toBe(false)
  })
})

describe('PanoramaDisplay', () => {
  it('renders the recorded facts and real expand arrows', () => {
    const result = parsePanorama(recorded('pharmacy-first-caps', 'panorama_search'))
    const w = mount(PanoramaDisplay, { props: { result, resultLength: 6594 } })
    expect(result.activeFacts.length).toBeGreaterThan(0)
    expect(w.text()).toContain(result.activeFacts[0])
    expect(w.html()).not.toMatch(MOJIBAKE)
  })
})
