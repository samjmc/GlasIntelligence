import { readFileSync } from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import { describe, it, expect } from 'vitest'
import { indexEntries, resolve } from './tape.js'

const here = path.dirname(fileURLToPath(import.meta.url))
const tape = JSON.parse(readFileSync(path.join(here, '../../public/demo/pharmacy-first-caps/tape.json'), 'utf8'))

describe('deployed R2 merged tape', () => {
  it('is well-formed', () => {
    expect(tape.schema_version).toBe(1)
    expect(tape.entries.length).toBeGreaterThan(300)
    const bad = tape.entries.filter(e => !e.t_ms || !e.method || !e.path || !('body' in e) || e.status === undefined)
    expect(bad).toEqual([])
  })
  it('serves the merged 49-node graph at end-of-tape', () => {
    const index = indexEntries(tape.entries)
    const r = resolve(index, 'GET', '/api/graph/data/demo-e2e-graph', tape.duration_ms)
    expect(r.body.success).toBe(true)
    const nodes = r.body.data.nodes
    expect(nodes.length).toBe(49)
    expect(r.body.data.node_count).toBe(49)
    const names = nodes.map(n => n.name)
    expect(names).toContain('Pharmaceutical Services Negotiating Committee (PSNC)')
    expect(names).toContain('Company Chemists\' Association (CCA)')
    expect(names).toContain('National Pharmacy Association (NPA)')
  })
})
