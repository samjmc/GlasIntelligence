import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const vuePath = path.join(__dirname, '../src/components/Step4Report.vue')
const outDir = path.join(__dirname, '../src/components/step4')
const lines = fs.readFileSync(vuePath, 'utf8').split(/\n/)

fs.mkdirSync(outDir, { recursive: true })

const toolBlock = lines
  .slice(1205, 1251)
  .join('\n')
  .replace(/^const toolConfig/, 'export const toolConfig')
  .replace(/^const getToolDisplayName/m, 'export const getToolDisplayName')
  .replace(/^const getToolColor/m, 'export const getToolColor')
  .replace(/^const getToolIcon/m, 'export const getToolIcon')
fs.writeFileSync(
  path.join(outDir, 'step4ReportToolConfig.js'),
  toolBlock + '\n',
  'utf8',
)

let parserBlock = lines.slice(1252, 1669).join('\n')
parserBlock = parserBlock
  .replace(/^const parseInsightForge/m, 'export const parseInsightForge')
  .replace(/^const parsePanorama/m, 'export const parsePanorama')
  .replace(/^const parseInterview/m, 'export const parseInterview')
  .replace(/^const parseQuickSearch/m, 'export const parseQuickSearch')
fs.writeFileSync(path.join(outDir, 'step4ReportParsers.js'), parserBlock + '\n', 'utf8')

let mdBody = lines.slice(2579, 2683).join('\n')
mdBody = mdBody.replace(/^const renderMarkdown = \(content\) => \{/, 'export function renderMarkdown(content) {')
fs.writeFileSync(
  path.join(outDir, 'step4ReportMarkdown.js'),
  `import DOMPurify from 'dompurify'\n\n${mdBody}\n`,
  'utf8',
)

let disp = lines.slice(1669, 2412).join('\n')
disp = `import { ref, computed, reactive, h } from 'vue'\nimport { renderMarkdown } from './step4ReportMarkdown.js'\n\n${disp}`
disp = disp
  .replace(/^const InsightDisplay/m, 'export const InsightDisplay')
  .replace(/^const PanoramaDisplay/m, 'export const PanoramaDisplay')
  .replace(/^const InterviewDisplay/m, 'export const InterviewDisplay')
  .replace(/^const QuickSearchDisplay/m, 'export const QuickSearchDisplay')
fs.writeFileSync(path.join(outDir, 'step4ReportToolDisplays.js'), disp + '\n', 'utf8')

console.log('Wrote step4 modules to', outDir)
