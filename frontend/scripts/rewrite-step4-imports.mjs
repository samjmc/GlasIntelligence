import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const vuePath = path.join(__dirname, '../src/components/Step4Report.vue')
const lines = fs.readFileSync(vuePath, 'utf8').split(/\n/)

const extraImports = `import {
  getToolDisplayName,
  getToolColor,
  getToolIcon,
} from './step4/step4ReportToolConfig.js'
import {
  parseInsightForge,
  parsePanorama,
  parseInterview,
  parseQuickSearch,
} from './step4/step4ReportParsers.js'
import { renderMarkdown } from './step4/step4ReportMarkdown.js'
import {
  InsightDisplay,
  PanoramaDisplay,
  InterviewDisplay,
  QuickSearchDisplay,
} from './step4/step4ReportToolDisplays.js'`

// Drop DOMPurify import (now only used in step4ReportMarkdown.js); line 1055 1-based = index 1054
const beforeDom = lines.slice(0, 1054).join('\n')
const afterDom = lines.slice(1055, 1205).join('\n')
const mid = lines.slice(2413, 2579).join('\n')
const tail = lines.slice(2683).join('\n')

const out = [beforeDom, extraImports, afterDom, mid, tail].join('\n\n') + '\n'
fs.writeFileSync(vuePath, out, 'utf8')
console.log('Rewrote', vuePath, 'lines:', out.split('\n').length)
