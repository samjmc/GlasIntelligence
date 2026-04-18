// Tool configurations with display names and colors
const toolConfig = {
  'insight_forge': {
    name: 'Deep Insight',
    color: 'purple',
    icon: 'lightbulb' // Lightbulb icon - represents insight
  },
  'panorama_search': {
    name: 'Panorama Search',
    color: 'blue',
    icon: 'globe' // Globe icon - represents panorama search
  },
  'interview_agents': {
    name: 'Agent Interview',
    color: 'green',
    icon: 'users' // Users icon - represents conversation
  },
  'quick_search': {
    name: 'Quick Search',
    color: 'orange',
    icon: 'zap' // Lightning icon - represents quick
  },
  'get_graph_statistics': {
    name: 'Graph Stats',
    color: 'cyan',
    icon: 'chart' // Chart icon - represents statistics
  },
  'get_entities_by_type': {
    name: 'Entity Query',
    color: 'pink',
    icon: 'database' // Database icon - represents entity
  }
}

export const getToolDisplayName = (toolName) => {
  return toolConfig[toolName]?.name || toolName
}

export const getToolColor = (toolName) => {
  return toolConfig[toolName]?.color || 'gray'
}

export const getToolIcon = (toolName) => {
  return toolConfig[toolName]?.icon || 'tool'
}

