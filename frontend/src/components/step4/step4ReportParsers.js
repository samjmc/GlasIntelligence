// Parsers for the report agent's tool results (the `details.result` text in the agent log).
// Every marker below must match the backend's to_text() output in
// backend/app/services/zep_tools.py: InsightForgeResult, PanoramaResult, InterviewResult /
// AgentInterview and SearchResult. They used to be Chinese markers that had been
// double-encoded (mojibake), so nothing matched and Step 4 showed no parsed details.

export const NO_RESPONSE_TEXT = '(No response received from this platform)'

export const parseInsightForge = (text) => {
  const result = {
    query: '',
    simulationRequirement: '',
    stats: { facts: 0, entities: 0, relationships: 0 },
    subQueries: [],
    facts: [],
    entities: [],
    relations: []
  }

  try {
    // Extract analysis question
    const queryMatch = text.match(/Analysis question:\s*(.+?)(?:\n|$)/)
    if (queryMatch) result.query = queryMatch[1].trim()

    // Extract prediction scenario
    const reqMatch = text.match(/Prediction scenario:\s*(.+?)(?:\n|$)/)
    if (reqMatch) result.simulationRequirement = reqMatch[1].trim()

    // Extract statistics - "- Related prediction facts: X" format
    const factMatch = text.match(/Related prediction facts:\s*(\d+)/)
    const entityMatch = text.match(/Entities involved:\s*(\d+)/)
    const relMatch = text.match(/Relationship chains:\s*(\d+)/)
    if (factMatch) result.stats.facts = parseInt(factMatch[1])
    if (entityMatch) result.stats.entities = parseInt(entityMatch[1])
    if (relMatch) result.stats.relationships = parseInt(relMatch[1])

    // Extract sub-questions - full extract, no limit
    const subQSection = text.match(/### Analysed Sub-queries\n([\s\S]*?)(?=\n###|$)/)
    if (subQSection) {
      const lines = subQSection[1].split('\n').filter(l => l.match(/^\d+\./))
      result.subQueries = lines.map(l => l.replace(/^\d+\.\s*/, '').trim()).filter(Boolean)
    }

    // Extract key facts - full extract, no limit
    const factsSection = text.match(/### \[Key Facts\][^\n]*\n([\s\S]*?)(?=\n###|$)/)
    if (factsSection) {
      const lines = factsSection[1].split('\n').filter(l => l.match(/^\d+\./))
      result.facts = lines.map(l => {
        const match = l.match(/^\d+\.\s*"?(.+?)"?\s*$/)
        return match ? match[1].replace(/^"|"$/g, '').trim() : l.replace(/^\d+\.\s*/, '').trim()
      }).filter(Boolean)
    }

    // Extract core entities - full extract, includes summary and related fact count
    const entitySection = text.match(/### \[Core Entities\]\n([\s\S]*?)(?=\n###|$)/)
    if (entitySection) {
      const entityText = entitySection[1]
      // Split entity blocks by "- **"
      const entityBlocks = entityText.split(/\n(?=- \*\*)/).filter(b => b.trim().startsWith('- **'))
      result.entities = entityBlocks.map(block => {
        const nameMatch = block.match(/^-\s*\*\*(.+?)\*\*\s*\((.+?)\)/)
        const summaryMatch = block.match(/Summary:\s*"?(.+?)"?(?:\n|$)/)
        const relatedMatch = block.match(/Related facts:\s*(\d+)/)
        return {
          name: nameMatch ? nameMatch[1].trim() : '',
          type: nameMatch ? nameMatch[2].trim() : '',
          summary: summaryMatch ? summaryMatch[1].trim() : '',
          relatedFactsCount: relatedMatch ? parseInt(relatedMatch[1]) : 0
        }
      }).filter(e => e.name)
    }

    // Extract relation chains - full extract, no limit
    const relSection = text.match(/### \[Relationship Chains\]\n([\s\S]*?)(?=\n###|$)/)
    if (relSection) {
      const lines = relSection[1].split('\n').filter(l => l.trim().startsWith('-'))
      result.relations = lines.map(l => {
        const match = l.match(/^-\s*(.+?)\s*--\[(.+?)\]-->\s*(.+)$/)
        if (match) {
          return { source: match[1].trim(), relation: match[2].trim(), target: match[3].trim() }
        }
        return null
      }).filter(Boolean)
    }
  } catch (e) {
    console.warn('Parse insight_forge failed:', e)
  }

  return result
}

export const parsePanorama = (text) => {
  const result = {
    query: '',
    stats: { nodes: 0, edges: 0, activeFacts: 0, historicalFacts: 0 },
    activeFacts: [],
    historicalFacts: [],
    entities: []
  }

  try {
    // Extract query
    const queryMatch = text.match(/^Query:\s*(.+?)(?:\n|$)/m)
    if (queryMatch) result.query = queryMatch[1].trim()

    // Extract statistics
    const nodesMatch = text.match(/Total nodes:\s*(\d+)/)
    const edgesMatch = text.match(/Total edges:\s*(\d+)/)
    const activeMatch = text.match(/Currently active facts:\s*(\d+)/)
    const histMatch = text.match(/Historical \/ expired facts:\s*(\d+)/)
    if (nodesMatch) result.stats.nodes = parseInt(nodesMatch[1])
    if (edgesMatch) result.stats.edges = parseInt(edgesMatch[1])
    if (activeMatch) result.stats.activeFacts = parseInt(activeMatch[1])
    if (histMatch) result.stats.historicalFacts = parseInt(histMatch[1])

    // Extract current valid facts - full extract, no limit
    const activeSection = text.match(/### \[Currently Active Facts\][^\n]*\n([\s\S]*?)(?=\n###|$)/)
    if (activeSection) {
      const lines = activeSection[1].split('\n').filter(l => l.match(/^\d+\./))
      result.activeFacts = lines.map(l => {
        // Remove numbering and quotes
        const factText = l.replace(/^\d+\.\s*/, '').replace(/^"|"$/g, '').trim()
        return factText
      }).filter(Boolean)
    }

    // Extract historical/expired facts - full extract, no limit
    const histSection = text.match(/### \[Historical \/ Expired Facts\][^\n]*\n([\s\S]*?)(?=\n###|$)/)
    if (histSection) {
      const lines = histSection[1].split('\n').filter(l => l.match(/^\d+\./))
      result.historicalFacts = lines.map(l => {
        const factText = l.replace(/^\d+\.\s*/, '').replace(/^"|"$/g, '').trim()
        return factText
      }).filter(Boolean)
    }

    // Extract involved entities - full extract, no limit
    const entitySection = text.match(/### \[Entities Involved\]\n([\s\S]*?)(?=\n###|$)/)
    if (entitySection) {
      const lines = entitySection[1].split('\n').filter(l => l.trim().startsWith('-'))
      result.entities = lines.map(l => {
        const match = l.match(/^-\s*\*\*(.+?)\*\*\s*\((.+?)\)/)
        if (match) return { name: match[1].trim(), type: match[2].trim() }
        return null
      }).filter(Boolean)
    }
  } catch (e) {
    console.warn('Parse panorama failed:', e)
  }

  return result
}

export const parseInterview = (text) => {
  const result = {
    topic: '',
    agentCount: '',
    successCount: 0,
    totalCount: 0,
    selectionReason: '',
    interviews: [],
    summary: ''
  }

  try {
    // Extract interview topic
    const topicMatch = text.match(/\*\*Interview topic:\*\*\s*(.+?)(?:\n|$)/)
    if (topicMatch) result.topic = topicMatch[1].trim()

    // Extract interview count (e.g. "**Interviewees:** 5 / 9 simulated agents")
    const countMatch = text.match(/\*\*Interviewees:\*\*\s*(\d+)\s*\/\s*(\d+)/)
    if (countMatch) {
      result.successCount = parseInt(countMatch[1])
      result.totalCount = parseInt(countMatch[2])
      result.agentCount = `${countMatch[1]} / ${countMatch[2]}`
    }

    // Extract interviewee selection reasons
    const reasonMatch = text.match(/### Interviewee Selection Rationale\n([\s\S]*?)(?=\n---\n|\n### Interview Transcripts)/)
    if (reasonMatch) {
      result.selectionReason = reasonMatch[1].trim()
    }

    // Parse each person's selection reason. The rationale is free LLM prose, so this only
    // finds per-person reasons when the model happens to list them in one of these forms.
    const parseIndividualReasons = (reasonText) => {
      const reasons = {}
      if (!reasonText) return reasons

      const lines = reasonText.split(/\n+/)
      let currentName = null
      let currentReason = []

      for (const line of lines) {
        // Format 1: "1. **name (index=X)**: reason"
        // Format 2: "- **name (index X)**: reason"
        const headerMatch =
          line.match(/^\d+\.\s*\*\*([^*(]+)(?:\(index\s*=?\s*\d+\))?\*\*:\s*(.*)/) ||
          line.match(/^-\s*\*\*([^*(]+)(?:\(index\s*=?\s*\d+\))?\*\*:\s*(.*)/)

        if (headerMatch) {
          // Save previous person's reason
          if (currentName && currentReason.length > 0) {
            reasons[currentName] = currentReason.join(' ').trim()
          }
          // Start the next person
          currentName = headerMatch[1].trim()
          currentReason = headerMatch[2] ? [headerMatch[2].trim()] : []
        } else if (currentName && line.trim()) {
          // Reason continuation
          currentReason.push(line.trim())
        }
      }

      // Save last person's reason
      if (currentName && currentReason.length > 0) {
        reasons[currentName] = currentReason.join(' ').trim()
      }

      return reasons
    }

    const individualReasons = parseIndividualReasons(result.selectionReason)

    // Extract each interview record. Each block ends at its "---" separator; the last one
    // would otherwise run on into the summary section.
    const interviewBlocks = text.split(/#### Interview #\d+:/).slice(1).map(b => b.split(/\n---\n/)[0])

    interviewBlocks.forEach((block, index) => {
      const interview = {
        num: index + 1,
        title: '',
        name: '',
        role: '',
        bio: '',
        selectionReason: '',
        questions: [],
        twitterAnswer: '',
        redditAnswer: '',
        quotes: []
      }

      // Extract title (the agent name after "#### Interview #N:")
      const titleMatch = block.match(/^(.+?)\n/)
      if (titleMatch) interview.title = titleMatch[1].trim()

      // Extract name and role
      const nameRoleMatch = block.match(/\*\*(.+?)\*\*\s*\((.+?)\)/)
      if (nameRoleMatch) {
        interview.name = nameRoleMatch[1].trim()
        interview.role = nameRoleMatch[2].trim()
        // Set this person's selection reason
        interview.selectionReason = individualReasons[interview.name] || ''
      }

      // Extract bio
      const bioMatch = block.match(/_Bio:\s*([\s\S]*?)_\n/)
      if (bioMatch) {
        interview.bio = bioMatch[1].trim()
      }

      // Extract question list
      const qMatch = block.match(/\*\*Q:\*\*\s*([\s\S]*?)(?=\n\n\*\*A:\*\*|\*\*A:\*\*)/)
      if (qMatch) {
        const qText = qMatch[1].trim()
        // Split questions by number
        const questions = qText.split(/\n\d+\.\s+/).filter(q => q.trim())
        if (questions.length > 0) {
          // If first question has "1." prefix, special handling
          const firstQ = qText.match(/^1\.\s+(.+)/)
          if (firstQ) {
            interview.questions = [firstQ[1].trim(), ...questions.slice(1).map(q => q.trim())]
          } else {
            interview.questions = questions.map(q => q.trim())
          }
        }
      }

      // Extract answer - one section per platform that answered (new runs are reddit only)
      const answerMatch = block.match(/\*\*A:\*\*\s*([\s\S]*?)(?=\n\*\*Key quotes:\*\*|$)/)
      if (answerMatch) {
        const answerText = answerMatch[1].trim()

        const twitterMatch = answerText.match(/\[Twitter Platform Response\]\n?([\s\S]*?)(?=\n*\[Reddit Platform Response\]|$)/)
        const redditMatch = answerText.match(/\[Reddit Platform Response\]\n?([\s\S]*?)$/)

        if (twitterMatch) {
          interview.twitterAnswer = twitterMatch[1].trim()
        }
        if (redditMatch) {
          interview.redditAnswer = redditMatch[1].trim()
        }

        // Platform fallback (single platform marker)
        if (!twitterMatch && redditMatch) {
          // Reddit only: copy as default when non-placeholder
          if (interview.redditAnswer && interview.redditAnswer !== NO_RESPONSE_TEXT) {
            interview.twitterAnswer = interview.redditAnswer
          }
        } else if (twitterMatch && !redditMatch) {
          if (interview.twitterAnswer && interview.twitterAnswer !== NO_RESPONSE_TEXT) {
            interview.redditAnswer = interview.twitterAnswer
          }
        } else if (!twitterMatch && !redditMatch) {
          // No platform marker, use whole as answer
          interview.twitterAnswer = answerText
        }
      }

      // Extract key quotes
      const quotesMatch = block.match(/\*\*Key quotes:\*\*\n([\s\S]*?)(?=\n---|\n####|$)/)
      if (quotesMatch) {
        const quotesText = quotesMatch[1]
        // Prefer > "text" format
        let quoteMatches = quotesText.match(/> "([^"]+)"/g)
        // Fallback: > \u201Ctext\u201D (curly quotes)
        if (!quoteMatches) {
          quoteMatches = quotesText.match(/> [\u201C"]([^\u201D"]+)[\u201D"]/g)
        }
        if (quoteMatches) {
          interview.quotes = quoteMatches
            .map(q => q.replace(/^> [\u201C"]|[\u201D"]$/g, '').trim())
            .filter(q => q)
        }
      }

      if (interview.name || interview.title) {
        result.interviews.push(interview)
      }
    })

    // Extract interview summary
    const summaryMatch = text.match(/### Interview Summary and Key Insights\n([\s\S]*)$/)
    if (summaryMatch) {
      result.summary = summaryMatch[1].trim()
    }
  } catch (e) {
    console.warn('Parse interview failed:', e)
  }

  return result
}

export const parseQuickSearch = (text) => {
  const result = {
    query: '',
    count: 0,
    facts: [],
    edges: [],
    nodes: []
  }

  try {
    // Extract search query
    const queryMatch = text.match(/Search query:\s*(.+?)(?:\n|$)/)
    if (queryMatch) result.query = queryMatch[1].trim()

    // Extract result count ("Found N relevant items")
    const countMatch = text.match(/Found\s*(\d+)\s*relevant/)
    if (countMatch) result.count = parseInt(countMatch[1])

    // Extract related facts - full extract, no limit
    const factsSection = text.match(/### Related facts:\n([\s\S]*?)(?=\n###|$)/)
    if (factsSection) {
      const lines = factsSection[1].split('\n').filter(l => l.match(/^\d+\./))
      result.facts = lines.map(l => l.replace(/^\d+\.\s*/, '').trim()).filter(Boolean)
    }

    // Try extract edge info (if any)
    const edgesSection = text.match(/### Related edges:\n([\s\S]*?)(?=\n###|$)/)
    if (edgesSection) {
      const lines = edgesSection[1].split('\n').filter(l => l.trim().startsWith('-'))
      result.edges = lines.map(l => {
        const match = l.match(/^-\s*(.+?)\s*--\[(.+?)\]-->\s*(.+)$/)
        if (match) {
          return { source: match[1].trim(), relation: match[2].trim(), target: match[3].trim() }
        }
        return null
      }).filter(Boolean)
    }

    // Try extract node info (if any)
    const nodesSection = text.match(/### Related nodes:\n([\s\S]*?)(?=\n###|$)/)
    if (nodesSection) {
      const lines = nodesSection[1].split('\n').filter(l => l.trim().startsWith('-'))
      result.nodes = lines.map(l => {
        const match = l.match(/^-\s*\*\*(.+?)\*\*\s*\((.+?)\)/)
        if (match) return { name: match[1].trim(), type: match[2].trim() }
        const simpleMatch = l.match(/^-\s*(.+)$/)
        if (simpleMatch) return { name: simpleMatch[1].trim(), type: '' }
        return null
      }).filter(Boolean)
    }
  } catch (e) {
    console.warn('Parse quick_search failed:', e)
  }

  return result
}
