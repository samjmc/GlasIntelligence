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
    // æå–åˆ†æžé—®é¢˜
    const queryMatch = text.match(/åˆ†æžé—®é¢˜:\s*(.+?)(?:\n|$)/)
    if (queryMatch) result.query = queryMatch[1].trim()
    
    // Extract prediction scenario
    const reqMatch = text.match(/é¢„æµ‹åœºæ™¯:\s*(.+?)(?:\n|$)/)
    if (reqMatch) result.simulationRequirement = reqMatch[1].trim()
    
    // Extract statistics - match "related prediction facts: X" format
    const factMatch = text.match(/ç›¸å…³é¢„æµ‹äº‹å®ž:\s*(\d+)/)
    const entityMatch = text.match(/æ¶‰åŠå®žä½“:\s*(\d+)/)
    const relMatch = text.match(/å…³ç³»é“¾:\s*(\d+)/)
    if (factMatch) result.stats.facts = parseInt(factMatch[1])
    if (entityMatch) result.stats.entities = parseInt(entityMatch[1])
    if (relMatch) result.stats.relationships = parseInt(relMatch[1])
    
    // Extract sub-questions - full extract, no limit
    const subQSection = text.match(/### åˆ†æžçš„å­é—®é¢˜\n([\s\S]*?)(?=\n###|$)/)
    if (subQSection) {
      const lines = subQSection[1].split('\n').filter(l => l.match(/^\d+\./))
      result.subQueries = lines.map(l => l.replace(/^\d+\.\s*/, '').trim()).filter(Boolean)
    }
    
    // Extract key facts - full extract, no limit
    const factsSection = text.match(/### ã€å…³é”®äº‹å®žã€‘[\s\S]*?\n([\s\S]*?)(?=\n###|$)/)
    if (factsSection) {
      const lines = factsSection[1].split('\n').filter(l => l.match(/^\d+\./))
      result.facts = lines.map(l => {
        const match = l.match(/^\d+\.\s*"?(.+?)"?\s*$/)
        return match ? match[1].replace(/^"|"$/g, '').trim() : l.replace(/^\d+\.\s*/, '').trim()
      }).filter(Boolean)
    }
    
    // Extract core entities - full extract, includes summary and related fact count
    const entitySection = null  // disabled: original Chinese regex was mojibake'd
    if (entitySection) {
      const entityText = entitySection[1]
      // Split entity blocks by "- **"
      const entityBlocks = entityText.split(/\n(?=- \*\*)/).filter(b => b.trim().startsWith('- **'))
      result.entities = entityBlocks.map(block => {
        const nameMatch = block.match(/^-\s*\*\*(.+?)\*\*\s*\((.+?)\)/)
        const summaryMatch = block.match(/æ‘˜è¦:\s*"?(.+?)"?(?:\n|$)/)
        const relatedMatch = block.match(/ç›¸å…³äº‹å®ž:\s*(\d+)/)
        return {
          name: nameMatch ? nameMatch[1].trim() : '',
          type: nameMatch ? nameMatch[2].trim() : '',
          summary: summaryMatch ? summaryMatch[1].trim() : '',
          relatedFactsCount: relatedMatch ? parseInt(relatedMatch[1]) : 0
        }
      }).filter(e => e.name)
    }
    
    // Extract relation chains - full extract, no limit
    const relSection = text.match(/### ã€å…³ç³»é“¾ã€‘\n([\s\S]*?)(?=\n###|$)/)
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
    const queryMatch = text.match(/æŸ¥è¯¢:\s*(.+?)(?:\n|$)/)
    if (queryMatch) result.query = queryMatch[1].trim()
    
    // Extract statistics
    const nodesMatch = text.match(/æ€»èŠ‚ç‚¹æ•°:\s*(\d+)/)
    const edgesMatch = text.match(/æ€»è¾¹æ•°:\s*(\d+)/)
    const activeMatch = text.match(/å½“å‰æœ‰æ•ˆäº‹å®ž:\s*(\d+)/)
    const histMatch = text.match(/åŽ†å²\/è¿‡æœŸäº‹å®ž:\s*(\d+)/)
    if (nodesMatch) result.stats.nodes = parseInt(nodesMatch[1])
    if (edgesMatch) result.stats.edges = parseInt(edgesMatch[1])
    if (activeMatch) result.stats.activeFacts = parseInt(activeMatch[1])
    if (histMatch) result.stats.historicalFacts = parseInt(histMatch[1])
    
    // Extract current valid facts - full extract, no limit
    const activeSection = text.match(/### ã€å½“å‰æœ‰æ•ˆäº‹å®žã€‘[\s\S]*?\n([\s\S]*?)(?=\n###|$)/)
    if (activeSection) {
      const lines = activeSection[1].split('\n').filter(l => l.match(/^\d+\./))
      result.activeFacts = lines.map(l => {
        // Remove numbering and quotes
        const factText = l.replace(/^\d+\.\s*/, '').replace(/^"|"$/g, '').trim()
        return factText
      }).filter(Boolean)
    }
    
    // Extract historical/expired facts - full extract, no limit
    const histSection = text.match(/### ã€åŽ†å²\/è¿‡æœŸäº‹å®žã€‘[\s\S]*?\n([\s\S]*?)(?=\n###|$)/)
    if (histSection) {
      const lines = histSection[1].split('\n').filter(l => l.match(/^\d+\./))
      result.historicalFacts = lines.map(l => {
        const factText = l.replace(/^\d+\.\s*/, '').replace(/^"|"$/g, '').trim()
        return factText
      }).filter(Boolean)
    }
    
    // Extract involved entities - full extract, no limit
    const entitySection = text.match(/### ã€æ¶‰åŠå®žä½“ã€‘\n([\s\S]*?)(?=\n###|$)/)
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
    const topicMatch = text.match(/\*\*é‡‡è®¿ä¸»é¢˜:\*\*\s*(.+?)(?:\n|$)/)
    if (topicMatch) result.topic = topicMatch[1].trim()
    
    // Extract interview count (e.g. "5 / 9 simulation agents")
    const countMatch = text.match(/\*\*é‡‡è®¿äººæ•°:\*\*\s*(\d+)\s*\/\s*(\d+)/)
    if (countMatch) {
      result.successCount = parseInt(countMatch[1])
      result.totalCount = parseInt(countMatch[2])
      result.agentCount = `${countMatch[1]} / ${countMatch[2]}`
    }
    
    // Extract interviewee selection reasons
    const reasonMatch = text.match(/### é‡‡è®¿å¯¹è±¡é€‰æ‹©ç†ç”±\n([\s\S]*?)(?=\n---\n|\n### é‡‡è®¿å®žå½•)/)
    if (reasonMatch) {
      result.selectionReason = reasonMatch[1].trim()
    }
    
    // Parse each person's selection reason
    const parseIndividualReasons = (reasonText) => {
      const reasons = {}
      if (!reasonText) return reasons
      
      const lines = reasonText.split(/\n+/)
      let currentName = null
      let currentReason = []
      
      for (const line of lines) {
        let headerMatch = null
        let name = null
        let reasonStart = null
        
        // Format 1: num. **name (index=X)**: reason
        // e.g. 1. **alumni_345 (index=1)**: As alumni...
        headerMatch = line.match(/^\d+\.\s*\*\*([^*ï¼ˆ(]+)(?:[ï¼ˆ(]index\s*=?\s*\d+[)ï¼‰])?\*\*[ï¼š:]\s*(.*)/)
        if (headerMatch) {
          name = headerMatch[1].trim()
          reasonStart = headerMatch[2]
        }
        
        // Format 2: - select name (index X): reason
        // e.g. - select parent_601 (index 0): As parent representative...
        if (!headerMatch) {
          headerMatch = line.match(/^-\s*é€‰æ‹©([^ï¼ˆ(]+)(?:[ï¼ˆ(]index\s*=?\s*\d+[)ï¼‰])?[ï¼š:]\s*(.*)/)
          if (headerMatch) {
            name = headerMatch[1].trim()
            reasonStart = headerMatch[2]
          }
        }
        
        // Format 3: - **name (index X)**: reason
        // e.g. - **parent_601 (index 0)**: As parent representative...
        if (!headerMatch) {
          headerMatch = line.match(/^-\s*\*\*([^*ï¼ˆ(]+)(?:[ï¼ˆ(]index\s*=?\s*\d+[)ï¼‰])?\*\*[ï¼š:]\s*(.*)/)
          if (headerMatch) {
            name = headerMatch[1].trim()
            reasonStart = headerMatch[2]
          }
        }
        
        if (name) {
          // Save previous person's reason
          if (currentName && currentReason.length > 0) {
            reasons[currentName] = currentReason.join(' ').trim()
          }
          // å¼€å§‹æ–°çš„äºº
          currentName = name
          currentReason = reasonStart ? [reasonStart.trim()] : []
        } else if (currentName && line.trim() && !line.match(/^æœªé€‰|^ç»¼ä¸Š|^æœ€ç»ˆé€‰æ‹©/)) {
          // Reason continuation (exclude final summary paragraphs)
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
    
    // Extract each interview record
    const interviewBlocks = text.split(/#### é‡‡è®¿ #\d+:/).slice(1)
    
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
      
      // Extract title (e.g. "student", "educator")
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
      const bioMatch = block.match(/_ç®€ä»‹:\s*([\s\S]*?)_\n/)
      if (bioMatch) {
        interview.bio = bioMatch[1].trim().replace(/\.\.\.$/, '...')
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
      
      // Extract answer - split Twitter and Reddit
      const answerMatch = block.match(/\*\*A:\*\*\s*([\s\S]*?)(?=\*\*å…³é”®å¼•è¨€|$)/)
      if (answerMatch) {
        const answerText = answerMatch[1].trim()
        
        // Split Twitter and Reddit answers
        const twitterMatch = answerText.match(/ã€Twitterå¹³å°å›žç­”ã€‘\n?([\s\S]*?)(?=ã€Redditå¹³å°å›žç­”ã€‘|$)/)
        const redditMatch = answerText.match(/ã€Redditå¹³å°å›žç­”ã€‘\n?([\s\S]*?)$/)
        
        if (twitterMatch) {
          interview.twitterAnswer = twitterMatch[1].trim()
        }
        if (redditMatch) {
          interview.redditAnswer = redditMatch[1].trim()
        }
        
        // Platform fallback (compat old format: single platform marker)
        if (!twitterMatch && redditMatch) {
          // Reddit only: copy as default when non-placeholder
          if (interview.redditAnswer && interview.redditAnswer !== 'ï¼ˆè¯¥å¹³å°æœªèŽ·å¾—å›žå¤ï¼‰') {
            interview.twitterAnswer = interview.redditAnswer
          }
        } else if (twitterMatch && !redditMatch) {
          if (interview.twitterAnswer && interview.twitterAnswer !== 'ï¼ˆè¯¥å¹³å°æœªèŽ·å¾—å›žå¤ï¼‰') {
            interview.redditAnswer = interview.twitterAnswer
          }
        } else if (!twitterMatch && !redditMatch) {
          // No platform marker (very old format), use whole as answer
          interview.twitterAnswer = answerText
        }
      }
      
      // Extract key quotes (compat multiple quote formats)
      const quotesMatch = block.match(/\*\*å…³é”®å¼•è¨€:\*\*\n([\s\S]*?)(?=\n---|\n####|$)/)
      if (quotesMatch) {
        const quotesText = quotesMatch[1]
        // Prefer > "text" format
        let quoteMatches = quotesText.match(/> "([^"]+)"/g)
        // Fallback: match > "text" or > \u201Ctext\u201D (Chinese quotes)
        if (!quoteMatches) {
          quoteMatches = quotesText.match(/> [\u201C""]([^\u201D""]+)[\u201D""]/g)
        }
        if (quoteMatches) {
          interview.quotes = quoteMatches
            .map(q => q.replace(/^> [\u201C""]|[\u201D""]$/g, '').trim())
            .filter(q => q)
        }
      }
      
      if (interview.name || interview.title) {
        result.interviews.push(interview)
      }
    })
    
    // Extract interview summary
    const summaryMatch = null  // disabled: original Chinese regex was mojibake'd
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
    const queryMatch = text.match(/æœç´¢æŸ¥è¯¢:\s*(.+?)(?:\n|$)/)
    if (queryMatch) result.query = queryMatch[1].trim()
    
    // Extract result count
    const countMatch = text.match(/æ‰¾åˆ°\s*(\d+)\s*æ¡/)
    if (countMatch) result.count = parseInt(countMatch[1])
    
    // Extract related facts - full extract, no limit
    const factsSection = text.match(/### ç›¸å…³äº‹å®ž:\n([\s\S]*)$/)
    if (factsSection) {
      const lines = factsSection[1].split('\n').filter(l => l.match(/^\d+\./))
      result.facts = lines.map(l => l.replace(/^\d+\.\s*/, '').trim()).filter(Boolean)
    }
    
    // Try extract edge info (if any)
    const edgesSection = text.match(/### ç›¸å…³è¾¹:\n([\s\S]*?)(?=\n###|$)/)
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
    const nodesSection = text.match(/### ç›¸å…³èŠ‚ç‚¹:\n([\s\S]*?)(?=\n###|$)/)
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

