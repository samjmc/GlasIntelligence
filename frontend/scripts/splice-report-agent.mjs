import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const p = path.join(__dirname, '../../backend/app/services/report_agent.py')
const lines = fs.readFileSync(p, 'utf8').split(/\n/)
// Remove lines 55-351 (1-based): indices 54-350 inclusive -> keep 0..53 and 351..
const head = lines.slice(0, 54).join('\n')
const tail = lines.slice(351).join('\n')
const insert = 'from .report_agent_logging import ReportLogger, ReportConsoleLogger\n'
const out = head + '\n' + insert + '\n' + tail + '\n'
fs.writeFileSync(p, out, 'utf8')
console.log('Spliced report_agent.py, new lines:', out.split('\n').length)
