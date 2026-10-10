import { describe, it, expect } from 'vitest'
import { renderMarkdown } from './step4ReportMarkdown.js'

const dossier = '## Key findings\n\nPrices **rose** sharply.\n\n- one\n- two'

describe('renderMarkdown', () => {
  it('drops a leading ## heading by default (report chapters show it elsewhere)', () => {
    const html = renderMarkdown(dossier)
    expect(html).not.toContain('Key findings')
    expect(html).toContain('<strong>rose</strong>')
  })

  it('keeps the leading heading when asked (the deep-research dossier reader)', () => {
    const html = renderMarkdown(dossier, { stripLeadingHeading: false })
    expect(html).toContain('<h3 class="md-h3">Key findings</h3>')
    expect(html).toContain('<strong>rose</strong>')
    expect(html).toContain('<ul class="md-ul">')
    expect(html).not.toContain('**')
    expect(html).not.toContain('##')
  })

  it('sanitizes HTML in the source', () => {
    const html = renderMarkdown('hello <img src=x onerror="alert(1)"><script>alert(2)</script>', {
      stripLeadingHeading: false,
    })
    expect(html).toContain('hello')
    expect(html).not.toContain('onerror')
    expect(html).not.toContain('<script')
  })
})
