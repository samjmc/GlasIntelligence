import { describe, it, expect, beforeEach, vi } from 'vitest'
import synthetic from './fixtures/synthetic-tape.json'
import {
  INTERVIEW_BATCH_PATH,
  REPORT_CHAT_PATH,
  UNRECORDED_ANSWER,
  isStep5Request,
  questionOf,
  step5Response,
} from './step5'

const BANK = {
  schema_version: 1,
  scenario: 'synthetic',
  generated_at: '2026-09-25T00:00:00+00:00',
  agent_questions: ['Why?', 'What next?'],
  agents: {
    0: { name: 'Pharmacist', answers: ['Because of the caps.', 'Protest.'] },
    1: { name: 'Treasury', answers: ['Cost control.', 'Hold firm.'] },
  },
  report_questions: ['Headline?'],
  report_answers: ['The caps backfire.'],
}

const batch = (interviews) => step5Response(BANK, 'POST', INTERVIEW_BATCH_PATH, JSON.stringify({ interviews }))

describe('step5Response', () => {
  it('answers each agent with its own recorded answer, in the live batch shape', () => {
    const { status, body } = batch([
      { agent_id: 0, prompt: 'Why?' },
      { agent_id: 1, prompt: 'What next?' },
    ])
    expect(status).toBe(200)
    expect(body.success).toBe(true)
    expect(body.data.mode).toBe('reconstructed')
    expect(body.data.result.interviews_count).toBe(2)
    expect(body.data.result.results).toEqual({
      reddit_0: { agent_id: 0, platform: 'reddit', response: 'Because of the caps.' },
      reddit_1: { agent_id: 1, platform: 'reddit', response: 'Hold firm.' },
    })
  })

  it('matches a recorded question despite case, spacing and the follow-up wrapper', () => {
    const wrapped = 'Here is our previous conversation:\nYou: Why?\nAgent: x\n\nMy new question is:   what  NEXT? '
    expect(batch([{ agent_id: 0, prompt: wrapped }]).body.data.result.results.reddit_0.response).toBe('Protest.')
  })

  it('says plainly when a question was not recorded', () => {
    expect(batch([{ agent_id: 0, prompt: 'Something new?' }]).body.data.result.results.reddit_0.response).toBe(
      UNRECORDED_ANSWER,
    )
  })

  it('reports an unknown agent as an error entry', () => {
    const entry = batch([{ agent_id: 9, prompt: 'Why?' }]).body.data.result.results.reddit_9
    expect(entry.response).toBeNull()
    expect(entry.error).toContain('not found')
  })

  it('answers the report agent in the live chat shape', () => {
    const { body } = step5Response(BANK, 'POST', REPORT_CHAT_PATH, { message: 'headline?' })
    expect(body).toEqual({ success: true, data: { response: 'The caps backfire.', tool_calls: [], sources: [] } })
  })

  it('leaves other requests to the tape', () => {
    expect(step5Response(BANK, 'GET', REPORT_CHAT_PATH, '{}')).toBeNull()
    expect(step5Response(BANK, 'POST', '/api/simulation/create', '{}')).toBeNull()
    expect(step5Response(null, 'POST', REPORT_CHAT_PATH, '{}')).toBeNull()
    expect(isStep5Request('POST', `${INTERVIEW_BATCH_PATH}?x=1`)).toBe(true)
    expect(isStep5Request('GET', INTERVIEW_BATCH_PATH)).toBe(false)
  })

  it('questionOf keeps a plain question as it is', () => {
    expect(questionOf('Why?')).toBe('Why?')
  })
})

describe('demoAdapter with recorded Step 5 answers', () => {
  beforeEach(() => {
    vi.resetModules()
    global.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} }
  })

  function serve(step5) {
    global.fetch = vi.fn(async (url) => {
      if (String(url).endsWith('/step5.json')) {
        return step5 ? { ok: true, status: 200, json: async () => step5 } : { ok: false, status: 404 }
      }
      return { ok: true, status: 200, json: async () => synthetic }
    })
  }

  it('serves the recorded answer for the agent and question in the request body', async () => {
    serve(BANK)
    const { demoAdapter, setActiveScenario } = await import('./adapter')
    setActiveScenario('synthetic')
    const res = await demoAdapter({
      url: INTERVIEW_BATCH_PATH,
      method: 'post',
      data: JSON.stringify({ simulation_id: 'x', interviews: [{ agent_id: 1, prompt: 'Why?' }] }),
    })
    expect(res.data.data.result.results.reddit_1.response).toBe('Cost control.')
  })

  it('falls back to the tape when the scenario recorded no Step 5 answers', async () => {
    serve(null)
    const { demoAdapter, setActiveScenario } = await import('./adapter')
    const { NOT_RECORDED } = await import('./tape')
    setActiveScenario('synthetic')
    const res = await demoAdapter({ url: REPORT_CHAT_PATH, method: 'post', data: '{"message":"Headline?"}' })
    expect(res.data.error).toBe(NOT_RECORDED)
  })
})
