<template>
  <Teleport to="body">
    <div v-if="modelValue" class="dm-overlay" @click.self="close">
      <div class="dm-modal">

        <div class="dm-header">
          <div class="dm-title-row">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <span class="dm-filename">{{ filename }}</span>
          </div>
          <div class="dm-tabs">
            <button class="dm-tab" :class="{ active: mode === 'preview' }" @click="mode = 'preview'">Preview</button>
            <button class="dm-tab" :class="{ active: mode === 'edit' }" @click="mode = 'edit'">Edit</button>
          </div>
          <button class="dm-close" @click="close">&times;</button>
        </div>

        <div class="dm-body">
          <div
            v-if="mode === 'preview'"
            class="dm-preview"
            v-html="rendered"
          />
          <textarea
            v-else
            class="dm-editor"
            v-model="draft"
            spellcheck="false"
          />
        </div>

        <div v-if="mode === 'edit'" class="dm-footer">
          <span class="dm-hint">Changes update the dossier used for this simulation.</span>
          <button class="dm-save" @click="save">Save</button>
        </div>

      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import DOMPurify from 'dompurify'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  content:    { type: String, default: '' },
  filename:   { type: String, default: 'dossier.md' },
})

const emit = defineEmits(['update:modelValue', 'save'])

const mode  = ref('preview')
const draft = ref(props.content)

watch(() => props.content, v => { draft.value = v })
watch(() => props.modelValue, v => { if (v) mode.value = 'preview' })

function close() { emit('update:modelValue', false) }
function save()  { emit('save', draft.value); emit('update:modelValue', false) }

// ── Markdown renderer ────────────────────────────────────────────────────────

function esc(t) {
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

function inline(t) {
  return esc(t)
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
}

function renderMarkdown(text) {
  if (!text) return ''
  const lines   = text.split('\n')
  let   html    = ''
  let   inList  = false
  let   inCode  = false
  let   codeBuf = ''

  for (const raw of lines) {
    const line = raw

    if (line.startsWith('```')) {
      if (inCode) {
        html  += `<pre><code>${esc(codeBuf.replace(/\n$/, ''))}</code></pre>`
        codeBuf = ''; inCode = false
      } else {
        if (inList) { html += '</ul>'; inList = false }
        inCode = true
      }
      continue
    }
    if (inCode) { codeBuf += raw + '\n'; continue }

    const t = line.trim()

    // Close list when a non-list line appears
    if (inList && !t.match(/^[-*\d]/)) { html += '</ul>'; inList = false }

    if (!t)                      { html += '<div class="dm-spacer"></div>'; continue }
    if (t === '---' || t === '***') { html += '<hr>'; continue }
    if (t.startsWith('#### '))   { html += `<h4>${inline(t.slice(5))}</h4>`; continue }
    if (t.startsWith('### '))    { html += `<h3>${inline(t.slice(4))}</h3>`; continue }
    if (t.startsWith('## '))     { html += `<h2>${inline(t.slice(3))}</h2>`; continue }
    if (t.startsWith('# '))      { html += `<h1>${inline(t.slice(2))}</h1>`; continue }

    if (t.match(/^[-*] /)) {
      if (!inList) { html += '<ul>'; inList = true }
      html += `<li>${inline(t.slice(2))}</li>`
      continue
    }
    if (t.match(/^\d+\. /)) {
      if (!inList) { html += '<ul>'; inList = true }
      html += `<li>${inline(t.replace(/^\d+\.\s*/, ''))}</li>`
      continue
    }

    html += `<p>${inline(t)}</p>`
  }

  if (inList) html += '</ul>'
  if (inCode) html += `<pre><code>${esc(codeBuf)}</code></pre>`
  return html
}

const rendered = computed(() =>
  DOMPurify.sanitize(renderMarkdown(props.content), { USE_PROFILES: { html: true } })
)
</script>

<style scoped>
.dm-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,0.75); backdrop-filter: blur(6px);
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.dm-modal {
  background: var(--bg-elevated, #161616);
  border: 1px solid var(--border, #2a2a2a);
  border-radius: 16px;
  width: 100%; max-width: 860px;
  max-height: 90vh;
  display: flex; flex-direction: column;
  overflow: hidden;
}

/* Header */
.dm-header {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border, #2a2a2a);
  flex-shrink: 0;
}
.dm-title-row {
  display: flex; align-items: center; gap: 8px;
  color: var(--text-secondary, #888); flex: 1; min-width: 0;
}
.dm-title-row svg { flex-shrink: 0; }
.dm-filename {
  font-size: 0.8rem; font-family: var(--font-mono, monospace);
  color: #ccc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.dm-tabs {
  display: flex; gap: 0;
  border: 1px solid var(--border, #333); border-radius: 7px; overflow: hidden;
}
.dm-tab {
  padding: 5px 16px; font-size: 0.78rem; font-weight: 600;
  background: transparent; border: none; color: var(--text-secondary, #666);
  cursor: pointer; transition: all 0.15s;
  font-family: var(--font-mono, monospace); text-transform: uppercase; letter-spacing: 0.4px;
}
.dm-tab:not(:last-child) { border-right: 1px solid var(--border, #333); }
.dm-tab.active { color: #fff; background: rgba(255,255,255,0.08); }
.dm-tab:hover:not(.active) { color: #ccc; }
.dm-close {
  background: none; border: none; color: var(--text-secondary, #888);
  font-size: 22px; line-height: 1; cursor: pointer; padding: 0 4px;
  flex-shrink: 0;
}
.dm-close:hover { color: #fff; }

/* Body */
.dm-body { flex: 1; overflow: hidden; display: flex; flex-direction: column; }

.dm-preview {
  flex: 1; overflow-y: auto; padding: 28px 36px;
  font-size: 0.88rem; line-height: 1.75; color: #ddd;
}
.dm-editor {
  flex: 1; width: 100%; box-sizing: border-box;
  resize: none; background: var(--bg, #0e0e0e);
  color: #ccc; border: none; outline: none;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-size: 0.82rem; line-height: 1.7;
  padding: 24px 28px;
  min-height: 0;
}

/* Footer */
.dm-footer {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px;
  border-top: 1px solid var(--border, #2a2a2a);
  flex-shrink: 0;
}
.dm-hint { font-size: 0.75rem; color: var(--text-secondary, #666); }
.dm-save {
  padding: 7px 22px; border-radius: 8px; font-weight: 600; font-size: 0.82rem;
  background: var(--accent, #00b894); color: #000; border: none; cursor: pointer;
  transition: filter 0.2s;
}
.dm-save:hover { filter: brightness(1.1); }

/* Preview markdown styles */
.dm-preview :deep(h1) { font-size: 1.35rem; font-weight: 700; color: #fff; margin: 0 0 12px; }
.dm-preview :deep(h2) {
  font-size: 1.05rem; font-weight: 700; color: var(--accent, #00b894);
  margin: 24px 0 8px; padding-bottom: 6px;
  border-bottom: 1px solid var(--border, #2a2a2a);
}
.dm-preview :deep(h3) { font-size: 0.92rem; font-weight: 700; color: #eee; margin: 16px 0 6px; }
.dm-preview :deep(h4) { font-size: 0.86rem; font-weight: 600; color: #ccc; margin: 12px 0 4px; }
.dm-preview :deep(p) { margin: 0 0 10px; }
.dm-preview :deep(ul) { padding-left: 20px; margin: 6px 0 12px; }
.dm-preview :deep(li) { margin-bottom: 4px; }
.dm-preview :deep(strong) { color: #fff; font-weight: 600; }
.dm-preview :deep(em) { color: #aaa; font-style: italic; }
.dm-preview :deep(code) {
  font-family: var(--font-mono, monospace); font-size: 0.8em;
  background: rgba(255,255,255,0.07); padding: 2px 5px; border-radius: 4px; color: #7ec8e3;
}
.dm-preview :deep(pre) {
  background: rgba(0,0,0,0.4); border: 1px solid var(--border, #2a2a2a);
  border-radius: 8px; padding: 14px 16px; overflow-x: auto; margin: 12px 0;
}
.dm-preview :deep(pre code) { background: none; padding: 0; color: #ccc; }
.dm-preview :deep(hr) { border: none; border-top: 1px solid var(--border, #2a2a2a); margin: 20px 0; }
.dm-preview :deep(.dm-spacer) { height: 6px; }
</style>
