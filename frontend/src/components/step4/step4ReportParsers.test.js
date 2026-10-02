import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { parseInsightForge, parseInterview, parsePanorama, parseQuickSearch } from './step4ReportParsers.js'
import generated from './__fixtures__/generatedToolResults.json'

// The parsers must read the text the backend actually writes (zep_tools.py to_text()).
// Their markers used to be double-encoded Chinese, so every parse came back empty.
// Recorded results come straight from the demo tapes; the two tools no tape recorded
// (insight_forge, quick_search) come from __fixtures__/generatedToolResults.json, which
// backend/scripts/gen_step4_parser_fixtures.py writes from the backend classes themselves.

const toolResults = (scenario, tool) => {
  // vitest runs from frontend/ (jsdom's import.meta.url is not a file path)
  const path = resolve(process.cwd(), 'public', 'demo', scenario, 'tape.json')
  const out = new Set()
  const walk = (o) => {
    if (Array.isArray(o)) return o.forEach(walk)
    if (!o || typeof o !== 'object') return
    if (o.details && o.details.tool_name === tool && typeof o.details.result === 'string') out.add(o.details.result)
    Object.values(o).forEach(walk)
  }
  walk(JSON.parse(readFileSync(path, 'utf8')))
  return [...out]
}

describe('parseInterview on recorded results', () => {
  const recorded = toolResults('energy-price-cap', 'interview_agents').sort((a, b) => b.length - a.length)

  it('finds the recordings this test relies on', () => {
    expect(recorded.length).toBeGreaterThan(0)
  })

  it('reads every interview, with name, role, bio, questions and both platform answers', () => {
    const text = recorded[0]
    const expected = (text.match(/#### Interview #\d+:/g) || []).length
    expect(expected).toBe(6)

    const r = parseInterview(text)
    expect(r.topic).toMatch(/^How is the January 2027 retail energy price cap/)
    expect([r.successCount, r.totalCount, r.agentCount]).toEqual([6, 11, '6 / 11'])
    expect(r.selectionReason).toMatch(/^The selected agents provide/)
    expect(r.interviews).toHaveLength(expected)

    const first = r.interviews[0]
    expect(first.name).toBe('energy_retail_companies_255')
    expect(first.role).toMatch(/trade association/)
    expect(first.bio).toMatch(/^We are the energy retail companies/)
    expect(first.questions).toHaveLength(5)
    expect(first.questions[0]).toMatch(/^How is the January 2027/)
    expect(first.twitterAnswer).toMatch(/^Question 1:/)
    expect(first.redditAnswer).toMatch(/^Question 1:/)
    // The platform sections must not bleed into each other or into the separator
    expect(first.twitterAnswer).not.toMatch(/Reddit Platform Response/)
    expect(r.interviews.every(i => !/\n---/.test(i.redditAnswer))).toBe(true)

    expect(r.summary.length).toBeGreaterThan(200)
    // The last interview must stop before the summary section
    expect(r.interviews[expected - 1].redditAnswer).not.toMatch(/Interview Summary and Key Insights/)
  })

  it('handles a run where no agent answered', () => {
    const empty = toolResults('pharmacy-first-caps', 'interview_agents').find(t => t.includes('(No interview records)'))
    expect(empty).toBeTruthy()
    const r = parseInterview(empty)
    expect([r.successCount, r.totalCount]).toEqual([0, 8])
    expect(r.interviews).toEqual([])
    expect(r.summary).toMatch(/timed out/)
  })
})

describe('parseInterview on a reddit-only run (as the backend writes it now)', () => {
  it('puts the reddit answer under both tabs and reads the key quotes', () => {
    const r = parseInterview(generated.interview_reddit_only)
    expect(r.interviews).toHaveLength(2)
    const [a, b] = r.interviews
    expect(a.name).toBe('NHSBSA')
    expect(a.redditAnswer).toMatch(/^Question 1: Payments are calculated/)
    expect(a.twitterAnswer).toBe(a.redditAnswer)
    expect(a.quotes).toEqual(['Payments are calculated only for consultations up to the cap.'])
    expect(b.redditAnswer).not.toMatch(/Interview Summary/)
    expect(r.summary).toBe('Both agents expect fewer consultations.')
  })
})

describe('parsePanorama on recorded results', () => {
  const recorded = toolResults('pharmacy-first-caps', 'panorama_search')

  it('reads stats, facts and entities, and the counts agree with the lists', () => {
    expect(recorded.length).toBeGreaterThan(0)
    for (const text of recorded) {
      const r = parsePanorama(text)
      expect(r.query.length).toBeGreaterThan(10)
      expect(r.stats.nodes).toBeGreaterThan(0)
      expect(r.activeFacts).toHaveLength(r.stats.activeFacts)
      expect(r.historicalFacts).toHaveLength(r.stats.historicalFacts)
      expect(r.entities.length).toBeGreaterThan(0)
      expect(r.activeFacts[0]).not.toMatch(/^"|"$/)
    }
  })
})

describe('parsers on results generated from the backend classes', () => {
  it('parseInsightForge', () => {
    const r = parseInsightForge(generated.insight_forge)
    expect(r.query).toBe('How do pharmacies respond to the caps?')
    expect(r.simulationRequirement).toBe('Pharmacy First payment caps')
    expect(r.stats).toEqual({ facts: 2, entities: 1, relationships: 1 })
    expect(r.subQueries).toEqual(['Which pharmacies cut hours?', 'Do GPs see more patients?'])
    expect(r.facts).toEqual(['Caps start in March 2026.', 'Band 6 is capped at 234.'])
    expect(r.entities).toEqual([
      { name: 'NHSBSA', type: 'Organization', summary: 'Pays pharmacies.', relatedFactsCount: 2 },
    ])
    expect(r.relations).toEqual([{ source: 'NHSBSA', relation: 'PAYS', target: 'Pharmacies' }])
  })

  it('parseQuickSearch', () => {
    const r = parseQuickSearch(generated.quick_search)
    expect(r.query).toBe('payment caps')
    expect(r.count).toBe(2)
    expect(r.facts).toEqual(['Caps start in March 2026.', 'Band 6 is capped at 234.'])
  })
})
