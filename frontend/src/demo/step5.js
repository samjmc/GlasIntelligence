// Step 5 (Deep Interaction) for the static demo.
//
// The tape resolver keys on method + path + query, never on the request body, so it
// cannot tell one interview question or agent from another. Step 5's answers were
// therefore recorded separately, by backend/scripts/build_demo_step5.py, into
// public/demo/<scenario>/step5.json: real reconstructed-interview answers for every
// agent to a fixed set of questions, and real report-agent answers to another set.
// This module serves them in the live response shapes. A scenario without the file
// falls through to the tape (NOT_RECORDED, as before).

export const STEP5_SCHEMA_VERSION = 1
export const INTERVIEW_BATCH_PATH = '/api/simulation/interview/batch'
export const REPORT_CHAT_PATH = '/api/report/chat'
export const UNRECORDED_ANSWER =
  'This demo replays recorded answers only, so it cannot answer new questions. ' +
  'Pick one of the recorded questions shown above the input.'

// Step5Interaction wraps follow-up agent questions in the conversation so far.
const FOLLOW_UP_MARKER = 'My new question is: '

const cache = new Map()

export async function loadStep5(scenario) {
  if (!scenario) return null
  if (cache.has(scenario)) return cache.get(scenario)
  const promise = (async () => {
    const res = await fetch(`${import.meta.env.BASE_URL}demo/${scenario}/step5.json`)
    if (res.status === 404) return null // this scenario recorded no Step 5 answers
    if (!res.ok) throw new Error(`Step 5 answers for "${scenario}" failed to load (${res.status})`)
    const bank = await res.json()
    if (bank.schema_version !== STEP5_SCHEMA_VERSION) {
      throw new Error(`Step 5 schema ${bank.schema_version} does not match expected ${STEP5_SCHEMA_VERSION}`)
    }
    return bank
  })()
  promise.catch(() => cache.delete(scenario))
  cache.set(scenario, promise)
  return promise
}

const normalise = (text) => String(text ?? '').trim().replace(/\s+/g, ' ').toLowerCase()

export function questionOf(prompt) {
  const text = String(prompt ?? '')
  const at = text.lastIndexOf(FOLLOW_UP_MARKER)
  return at === -1 ? text : text.slice(at + FOLLOW_UP_MARKER.length)
}

function answerFor(questions, answers, prompt) {
  const index = questions.map(normalise).indexOf(normalise(questionOf(prompt)))
  return index === -1 ? UNRECORDED_ANSWER : answers[index]
}

function parseBody(body) {
  if (body && typeof body === 'object') return body
  try {
    return JSON.parse(body || '{}')
  } catch {
    return {}
  }
}

// Returns { status, body } for a Step 5 request, or null for any other request.
export function step5Response(bank, method, url, rawBody) {
  const path = String(url).split('?')[0]
  if (method !== 'POST' || !bank) return null
  const request = parseBody(rawBody)

  if (path.endsWith(REPORT_CHAT_PATH)) {
    const response = answerFor(bank.report_questions, bank.report_answers, request.message)
    return { status: 200, body: { success: true, data: { response, tool_calls: [], sources: [] } } }
  }

  if (path.endsWith(INTERVIEW_BATCH_PATH)) {
    const results = {}
    for (const { agent_id: agentId, prompt } of request.interviews || []) {
      const agent = bank.agents[String(agentId)]
      results[`reddit_${agentId}`] = agent
        ? { agent_id: agentId, platform: 'reddit', response: answerFor(bank.agent_questions, agent.answers, prompt) }
        : { agent_id: agentId, platform: 'reddit', response: null, error: `Agent ${agentId} not found on reddit` }
    }
    const count = Object.keys(results).length
    return {
      status: 200,
      body: {
        success: true,
        data: {
          mode: 'reconstructed',
          interviews_count: count,
          result: { interviews_count: count, results },
          timestamp: bank.generated_at,
        },
      },
    }
  }
  return null
}

export function isStep5Request(method, url) {
  const path = String(url).split('?')[0]
  return method === 'POST' && (path.endsWith(REPORT_CHAT_PATH) || path.endsWith(INTERVIEW_BATCH_PATH))
}
