/**
 * Move <style scoped>...</style> body to ./<Component>.scoped.css and replace with <style scoped src="...">.
 * Usage: node scripts/extract-vue-style.mjs path/to/Component.vue
 */
import fs from 'fs'
import path from 'path'

const vuePath = process.argv[2]
if (!vuePath) {
  console.error('Usage: node scripts/extract-vue-style.mjs <file.vue>')
  process.exit(1)
}

const lines = fs.readFileSync(vuePath, 'utf8').split(/\n/)
const styleIdx = lines.findIndex((l) => l.trim() === '<style scoped>')
if (styleIdx < 0) {
  console.error('No <style scoped> in', vuePath)
  process.exit(1)
}
const endIdx = lines.findIndex((l, i) => i > styleIdx && l.trim() === '</style>')
if (endIdx < 0) {
  console.error('No </style> in', vuePath)
  process.exit(1)
}

const css = lines.slice(styleIdx + 1, endIdx).join('\n')
const base = path.basename(vuePath, '.vue')
const dir = path.dirname(vuePath)
const cssName = `${base}.scoped.css`
const cssPath = path.join(dir, cssName)
fs.writeFileSync(cssPath, css + '\n', 'utf8')

const head = lines.slice(0, styleIdx).join('\n')
const rel = `./${cssName}`
const out = `${head}\n<style scoped src="${rel}"></style>\n`
fs.writeFileSync(vuePath, out, 'utf8')
console.log('Extracted', cssPath, `(${css.split('\n').length} lines)`)
