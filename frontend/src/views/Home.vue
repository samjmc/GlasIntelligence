<template>
  <div class="home-container">
    <AppNavbar />

    <div class="main-content">
      <section class="hero-section anim-fade" style="--delay: 0s">
        <div class="hero-left">
          <div class="tag-row">
            <span class="accent-tag">Multi-Agent Scenario Intelligence</span>
            <span class="version-text">/ v1.0</span>
          </div>

          <h1 class="main-title">
            Describe any scenario<br>
            <span class="gradient-text">{{ typewriterText }}<span v-if="!typewriterDone" class="tw-cursor">|</span></span>
          </h1>

          <div class="hero-desc">
            <p>
              Describe a scenario and <span class="highlight-bold">Glas Intelligence</span> guides you through gathering source materials, then creates <span class="highlight-accent">AI agents</span> who simulate stakeholder reactions over time. Discover how complex situations <span class="highlight-code">evolve</span>.
            </p>
            <p class="slogan-text">
              Scenario intelligence powered by multi-agent simulation<span class="blinking-cursor">_</span>
            </p>
          </div>

          <div class="decoration-square"></div>
        </div>

        <div class="hero-right">
          <div class="logo-container">
            <img src="../assets/logo/glas-logo.png" alt="Glas Intelligence Logo" class="hero-logo" />
          </div>
          <button class="scroll-down-btn" @click="scrollToBottom">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
        </div>
      </section>

      <section class="dashboard-section">
        <div class="left-panel anim-fade" :class="{ collapsed: leftPanelCollapsed }" style="--delay: .15s">
          <div class="panel-header">
            <span class="pulse-dot"></span>
            <span v-if="!leftPanelCollapsed">System Status</span>
          </div>

          <button class="left-panel-toggle" @click="leftPanelCollapsed = !leftPanelCollapsed" :title="leftPanelCollapsed ? 'Expand panel' : 'Collapse panel'">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline :points="leftPanelCollapsed ? '9 18 15 12 9 6' : '15 18 9 12 15 6'"/>
            </svg>
          </button>

          <div class="left-panel-content" v-show="!leftPanelCollapsed">
            <h2 class="section-title">Ready</h2>
            <p class="section-desc">
              Prediction engine on standby. Describe a scenario to begin.
            </p>

            <div class="metrics-row">
              <div class="metric-card">
                <div class="metric-icon">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                </div>
                <div class="metric-value">{{ planLimits.agents }}</div>
                <div class="metric-label">Agents per simulation</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                </div>
                <div class="metric-value">{{ planLimits.rounds }}</div>
                <div class="metric-label">Decision rounds</div>
              </div>
            </div>

            <div class="steps-container">
              <div class="steps-header">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></svg>
                Getting Started
              </div>
              <div class="guide-list">
                <div class="guide-item">
                  <span class="guide-number">1</span>
                  <div class="guide-info">
                    <div class="guide-title">Describe Your Scenario</div>
                    <div class="guide-desc">Enter the situation or decision you want to simulate</div>
                  </div>
                </div>
                <div class="guide-item">
                  <span class="guide-number">2</span>
                  <div class="guide-info">
                    <div class="guide-title">Configure Scenarios</div>
                    <div class="guide-desc">Define base, optimistic, and pessimistic variations to compare outcomes side-by-side</div>
                  </div>
                </div>
                <div class="guide-item">
                  <span class="guide-number">3</span>
                  <div class="guide-info">
                    <div class="guide-title">Run Deep Research</div>
                    <div class="guide-desc">AI searches the web for real-time data relevant to each scenario — often 30–40 min; allow up to ~40 min</div>
                  </div>
                </div>
                <div class="guide-item">
                  <span class="guide-number">4</span>
                  <div class="guide-info">
                    <div class="guide-title">Add Supporting Documents</div>
                    <div class="guide-desc">Upload reports, filings, or data to enrich the simulation context</div>
                  </div>
                </div>
                <div class="guide-item">
                  <span class="guide-number">5</span>
                  <div class="guide-info">
                    <div class="guide-title">Start Engine</div>
                    <div class="guide-desc">Launch the simulation once your scenarios, research, and documents are set</div>
                  </div>
                </div>
              </div>
            </div>

            <div class="steps-container">
              <div class="steps-header">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                Under the Hood
              </div>
              <div class="workflow-list">
                <div class="workflow-item">
                  <div class="step-icon-wrap">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
                  </div>
                  <div class="step-info">
                    <div class="step-title">Knowledge Graph</div>
                    <div class="step-desc">Document analysis, entity extraction, and knowledge graph construction</div>
                  </div>
                </div>
                <div class="workflow-item">
                  <div class="step-icon-wrap">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
                  </div>
                  <div class="step-info">
                    <div class="step-title">Environment Setup</div>
                    <div class="step-desc">Entity extraction, persona generation, and simulation configuration</div>
                  </div>
                </div>
                <div class="workflow-item">
                  <div class="step-icon-wrap">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                  </div>
                  <div class="step-info">
                    <div class="step-title">Run Simulation</div>
                    <div class="step-desc">Dual-platform parallel simulation with dynamic temporal memory</div>
                  </div>
                </div>
                <div class="workflow-item">
                  <div class="step-icon-wrap">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                  </div>
                  <div class="step-info">
                    <div class="step-title">Report Generation</div>
                    <div class="step-desc">Report Agent uses specialized tools to analyze simulation data</div>
                  </div>
                </div>
                <div class="workflow-item">
                  <div class="step-icon-wrap">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                  </div>
                  <div class="step-info">
                    <div class="step-title">Deep Interaction</div>
                    <div class="step-desc">Interview any simulated agent or chat with the Report Agent</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="right-panel anim-fade" style="--delay: .3s">
          <!-- Active Sessions Panel -->
          <div v-if="activeSessions.length > 0" class="sessions-panel">
            <div class="sessions-panel-header">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
              <span>Active Sessions</span>
              <span class="sessions-count">{{ activeSessions.length }}</span>
            </div>
            <div class="sessions-list">
              <div
                v-for="s in activeSessions"
                :key="s.id"
                class="session-card"
                :class="{ active: activeSessionId === s.id }"
                @click="restoreFromSession(s)"
              >
                <div class="session-card-top">
                  <span class="session-status-badge" :class="[s.status, s.research_status === 'failed' ? 'research-failed' : '', s.status === 'sim_failed' ? 'sim-failed' : '']">{{ sessionStatusLabel(s) }}</span>
                  <span class="session-time">{{ timeAgo(s.created_at) }}</span>
                </div>
                <div class="session-card-prompt">{{ s.prompt?.slice(0, 80) }}{{ s.prompt?.length > 80 ? '...' : '' }}</div>
                <button class="session-abandon-btn" @click.stop="handleAbandonSession(s.id)" title="Abandon session">&times;</button>
              </div>
            </div>
          </div>

          <div class="console-box">
            <div class="console-section">
              <div class="console-header">
                <span class="console-label">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
                  01 / Describe Your Scenario
                </span>
                <button
                  class="enhance-btn"
                  :disabled="!formData.simulationRequirement.trim() || loading || enhancing"
                  @click="handleEnhancePrompt"
                >
                  <span v-if="!enhancing">Enhance</span>
                  <span v-else>Enhancing...</span>
                </button>
              </div>
              <div class="input-wrapper">
                <textarea
                  v-model="formData.simulationRequirement"
                  class="code-input"
                  placeholder="What happens if Ofgem removes the energy price cap? What if the US imposes new tariffs on EU goods?"
                  rows="5"
                  :disabled="loading"
                ></textarea>
                <div class="model-badge">Engine: GLAS v1.0</div>
              </div>
            </div>

            <!-- Starter Scenario Cards (shown when textarea is empty) -->
            <div v-if="!formData.simulationRequirement.trim()" class="starter-scenarios">
              <div class="starter-header">Try an example</div>
              <div class="starter-cards">
                <button
                  v-for="(ex, i) in starterExamples"
                  :key="i"
                  class="starter-card"
                  @click="formData.simulationRequirement = ex.scenario"
                >
                  <span class="starter-icon">{{ ex.icon }}</span>
                  <span class="starter-text">{{ ex.label }}</span>
                </button>
              </div>
            </div>


            <template v-if="formData.simulationRequirement.trim()">
              <div class="console-section">
                <!-- Decision Context Form -->
                <div class="console-divider inner-divider" style="margin-top: 12px;">
                  <span>Decision Context (Optional)</span>
                </div>
                <div class="decision-context-form">
                  <div class="decision-field">
                    <label class="decision-label">Your Role</label>
                    <input v-model="decisionForm.role" class="decision-input" placeholder="e.g. Head of Strategy, Portfolio Manager, Policy Analyst" />
                  </div>
                  <div class="decision-field">
                    <label class="decision-label">Decision Question</label>
                    <input v-model="decisionForm.decision" class="decision-input" placeholder="e.g. Should we proceed with the acquisition?" />
                  </div>
                  <div class="decision-field">
                    <label class="decision-label">Constraints</label>
                    <input v-model="decisionForm.constraints" class="decision-input" placeholder="e.g. Budget cap of $5M, must decide by Q3" />
                  </div>
                  <div class="decision-field">
                    <label class="decision-label">Flip Conditions</label>
                    <input v-model="decisionForm.flip_conditions" class="decision-input" placeholder="e.g. If market cap drops below $10B, reverse decision" />
                  </div>
                  <div v-if="prefillRestored" class="prefill-restored-hint">
                    ↩ Restored from previous simulation
                  </div>
                </div>
              </div>

              <div class="console-section bundle-toggle-section" v-if="isPaidUser">
                <label class="bundle-toggle" :class="{ disabled: researchLoading }">
                  <input type="checkbox" v-model="fullAnalysisMode" :disabled="researchLoading" />
                  <span class="bundle-toggle-label">Run Full Decision Analysis</span>
                  <span class="bundle-toggle-hint">Generate multiple scenario variations for comprehensive analysis</span>
                </label>
              </div>

              <div v-if="fullAnalysisMode" class="console-section bundle-controls">
                <div class="bundle-controls-row">
                  <label class="bundle-count-label">
                    Scenarios
                    <select v-model="scenarioCount" class="bundle-count-select" :disabled="bundleLoading">
                      <option v-for="n in [2,3,4,5,6,7]" :key="n" :value="n">{{ n }}</option>
                    </select>
                  </label>
                  <button class="bundle-generate-btn" @click="generateScenarios" :disabled="bundleLoading || !formData.simulationRequirement.trim()">
                    <span v-if="bundleLoading"><span class="bundle-spinner-inline"></span> Generating...</span>
                    <span v-else-if="bundlePlan.length > 0">Regenerate</span>
                    <span v-else>Generate Scenarios</span>
                  </button>
                </div>
              </div>

              <div v-if="fullAnalysisMode && bundlePlan.length > 0" class="console-section bundle-editor">
                <div class="bundle-editor-header">
                  <span class="bundle-preview-label">Analysis Plan</span>
                  <span class="bundle-preview-count">{{ bundlePlan.length }} scenario{{ bundlePlan.length !== 1 ? 's' : '' }} · {{ bundlePlan.length }} credit{{ bundlePlan.length !== 1 ? 's' : '' }}</span>
                </div>
                <div class="bundle-editor-list">
                  <div v-for="(s, i) in bundlePlan" :key="i" class="bundle-editor-item" :style="{ '--item-delay': (i * 0.06) + 's' }">
                    <div class="bundle-editor-item-accent"></div>
                    <div class="bundle-editor-item-body">
                      <div class="bundle-editor-item-header">
                        <span class="bundle-preview-idx">{{ String(i + 1).padStart(2, '0') }}</span>
                        <input class="bundle-title-input" v-model="bundlePlan[i].title" placeholder="Scenario title" :disabled="researchLoading" />
                        <button class="bundle-remove-btn" @click="removeScenario(i)" :disabled="bundlePlan.length <= 2" title="Remove scenario">
                          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3.5 3.5l7 7M10.5 3.5l-7 7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
                        </button>
                      </div>
                      <textarea class="bundle-scenario-textarea" v-model="bundlePlan[i].scenario" placeholder="Describe this scenario variation..." rows="3" :disabled="researchLoading"></textarea>
                    </div>
                  </div>
                </div>
                <button v-if="bundlePlan.length < 7" class="bundle-add-btn" @click="addScenario" :disabled="researchLoading">
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 2v10M2 7h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
                  Add Scenario
                </button>
              </div>

              <div class="console-section">
                <div class="console-divider inner-divider">
                  <span>Upload Additional Documents</span>
                </div>

                <div class="console-header">
                  <span class="console-label">Supported formats: PDF, MD, TXT</span>
                </div>

                <div
                  class="upload-zone"
                  :class="{ 'drag-over': isDragOver, 'has-files': files.length > 0 }"
                  @dragover.prevent="handleDragOver"
                  @dragleave.prevent="handleDragLeave"
                  @drop.prevent="handleDrop"
                  @click="triggerFileInput"
                >
                  <input
                    ref="fileInput"
                    type="file"
                    multiple
                    accept=".pdf,.md,.txt"
                    @change="handleFileSelect"
                    style="display: none"
                    :disabled="loading"
                  />

                  <div v-if="files.length === 0" class="upload-placeholder">
                    <div class="upload-icon">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    </div>
                    <div class="upload-title">Drag and drop files</div>
                    <div class="upload-hint">or click to browse</div>
                  </div>

                  <div v-else class="file-list">
                    <div v-for="(file, index) in files" :key="index" class="file-item">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>
                      <span class="file-name file-name-link" @click.stop="openFile(file)">{{ file.name }}</span>
                      <button @click.stop="removeFile(index)" class="remove-btn">&times;</button>
                    </div>
                  </div>
                </div>

                <!-- Deep Research Button -->
                <div class="research-btn-row">
                  <button
                    class="auto-research-btn"
                    :class="{ disabled: !isPaidUser }"
                    :disabled="researchLoading"
                    @click="runDeepResearch"
                    :title="isPaidUser ? 'Launch deep research with AI web search' : 'Upgrade to Pro or Business to unlock deep research'"
                  >
                    <span v-if="!researchLoading">
                      {{ isPaidUser ? 'Deep Research Briefing' : 'Deep Research (Paid Plans)' }}
                      <span v-if="isPaidUser && researchCredits !== null" class="research-credits-badge">{{ researchCredits }}</span>
                    </span>
                    <span v-else class="research-loading-content">
                      <span class="progress-bar-track">
                        <span class="progress-bar-fill" :style="{ width: researchEstimatedProgress + '%' }"></span>
                      </span>
                      {{ researchStatusMessage }} — {{ researchEstimatedProgress }}% ({{ researchElapsedFormatted }})
                    </span>
                  </button>
                  <button
                    v-if="isPaidUser"
                    class="research-settings-btn"
                    :class="{ 'has-overrides': Object.keys(researchAngleOverrides).length > 0 }"
                    :disabled="researchLoading"
                    title="Configure research focus areas"
                    @click="showResearchSettings = true"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                    </svg>
                  </button>
                </div>

                <div class="research-info-callout" :class="{ active: researchLoading }">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                  <div class="research-info-text">
                    <template v-if="researchLoading">
                      <strong>Research in progress.</strong> The AI agent is searching the web, reading sources, and synthesizing findings. Complex topics often take <strong>30–40 minutes</strong>; allow <strong>up to about 40 minutes</strong>. You can leave this tab open — progress is tracked automatically.
                    </template>
                    <template v-else>
                      Launches an AI research agent that searches the web for real-time data, precedents, and quantitative anchors. If you have configured scenario variations above, research will target data relevant to each one. Typically takes 10–20 min.
                    </template>
                  </div>
                </div>

                <ResearchSettingsModal
                  v-model="showResearchSettings"
                  v-model:angleOverrides="researchAngleOverrides"
                />

                <!-- Buy Research Modal -->
                <div v-if="showBuyResearchModal" class="buy-research-overlay" @click.self="showBuyResearchModal = false">
                  <div class="buy-research-modal">
                    <button class="modal-close" @click="showBuyResearchModal = false">&times;</button>
                    <div class="modal-icon">
                      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                    </div>
                    <h3>No research credits remaining</h3>
                    <p class="modal-desc">Purchase additional research briefings to continue.</p>
                    <div class="buy-options">
                      <button class="buy-option primary" :disabled="buyingResearch" @click="handleBuyResearch('research_1')">
                        <span class="buy-qty">1 briefing</span>
                        <span class="buy-price">$7</span>
                      </button>
                      <button class="buy-option secondary" :disabled="buyingResearch" @click="handleBuyResearch('research_5')">
                        <span class="buy-qty">5 briefings</span>
                        <span class="buy-price">$30</span>
                        <span class="buy-save">Save $5</span>
                      </button>
                    </div>
                  </div>
                </div>

                <div v-if="error" class="research-error">{{ error }}</div>

                <div v-if="briefing" class="briefing-preview" :class="{ 'briefing-empty': !briefingHasContent }">
                  <div class="briefing-header">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <span class="briefing-title" :class="{ 'briefing-title-link': briefingHasContent }" @click="briefingHasContent && (showDossierModal = true)">{{ briefing.filename }}</span>
                    <button
                      v-if="briefingHasContent"
                      class="briefing-toggle"
                      @click="showDossierModal = true"
                    >
                      Read
                    </button>
                    <button
                      v-else
                      class="briefing-toggle briefing-toggle-retry"
                      :disabled="researchLoading"
                      @click="retryEmptyResearch"
                      title="The previous research returned no content. Click to retry."
                    >
                      Retry
                    </button>
                    <button class="remove-btn" @click="removeBriefing">&times;</button>
                  </div>
                  <div class="briefing-content">
                    <template v-if="!briefingHasContent">
                      <span class="briefing-empty-msg">
                        Research completed but returned no content. This is a known intermittent issue with the research agent — click <strong>Retry</strong> above to run it again (your credit is preserved on failure).
                      </span>
                    </template>
                    <template v-else>
                      <span class="briefing-snippet">{{ briefing.content_md.slice(0, 220) }}{{ briefing.content_md.length > 220 ? '…' : '' }}</span>
                    </template>
                  </div>
                </div>

                <DossierModal
                  v-model="showDossierModal"
                  :content="briefing?.content_md || ''"
                  :filename="briefing?.filename || 'deep_research_dossier.md'"
                  @save="onDossierSave"
                />
              </div>


              <div class="console-section btn-section">
                <button
                  class="start-engine-btn"
                  @click="startSimulation"
                  :disabled="!canSubmit || loading || researchLoading || bundleLoading"
                >
                  <span v-if="!loading">{{ fullAnalysisMode ? 'Start Full Analysis' : 'Start Engine' }}</span>
                  <span v-else>Initializing...</span>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                </button>
                <div v-if="formData.simulationRequirement.trim() && !files.length && !briefing" class="submit-hint">
                  Run Deep Research or upload a document to continue
                </div>
              </div>
            </template>
          </div>
        </div>
      </section>

      <HistoryDatabase />
    </div>

    <!-- Upgrade Modal -->
    <Teleport to="body">
      <div v-if="showUpgradeModal" class="modal-overlay" @click.self="showUpgradeModal = false">
        <div class="upgrade-modal">
          <button class="modal-close" @click="showUpgradeModal = false">&times;</button>
          <div class="modal-icon">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          </div>
          <h3 class="modal-title">Custom Simulations Require a Plan</h3>
          <p class="modal-desc">Upgrade to Pro or Business to run custom scenario simulations with AI agents, deep research, and quantified decision reports.</p>
          <div class="modal-actions">
            <button class="modal-btn primary" @click="router.push('/pricing')">View Plans</button>
            <button class="modal-btn secondary" @click="router.push('/feed')">Browse Free Reports</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import HistoryDatabase from '../components/HistoryDatabase.vue'
import AppNavbar from '../components/AppNavbar.vue'
import ResearchSettingsModal from '../components/ResearchSettingsModal.vue'
import DossierModal from '../components/DossierModal.vue'
import { authState, refreshAccessToken } from '../store/auth'
import { useApi } from '../composables/useApi'
import {
  createBundle, updateBundle,
  createSession, getActiveSessions, getSession, updateSession,
  uploadSessionFiles, startSessionResearch, getSessionResearchStatus, abandonSession,
  canResearch, buyResearchCredits,
} from '../api/simulation'
import { getPendingUpload, clearPendingUpload, setPendingUpload } from '../store/pendingUpload'
import { trackEvent } from '../lib/analytics'

const router = useRouter()
const route = useRoute()
const { apiGet, apiPost } = useApi()

const formData = ref({ simulationRequirement: '' })
const files = ref([])
const loading = ref(false)
const error = ref('')
const isDragOver = ref(false)
const fileInput = ref(null)

const enhancing = ref(false)
const showUpgradeModal = ref(false)
const researchLoading = ref(false)
const briefing = ref(null)
const showDossierModal = ref(false)
const briefingHasContent = computed(() => !!(briefing.value?.content_md || '').trim())
const leftPanelCollapsed = ref(false)

const typewriterText = ref('')
const typewriterDone = ref(false)

/** Align with API Config.normalize_plan — avoids 'Enterprise' vs 'enterprise' and null plan bugs. */
function normalizeClientPlan(raw) {
  if (raw == null || raw === '') return 'free'
  const s = String(raw).trim().toLowerCase()
  if (s === 'null' || s === 'undefined' || s === 'none') return 'free'
  return s
}

const userPlan = ref('free')
const prefillRestored = ref(false)
const decisionForm = reactive({
  role: '',
  decision: '',
  constraints: '',
  flip_conditions: '',
})
const researchDossier = ref(null)
const researchStatusMessage = ref('Researching...')
const researchElapsed = ref(0)
let researchElapsedTimer = null
const researchElapsedFormatted = computed(() => {
  const t = researchElapsed.value
  const m = Math.floor(t / 60)
  const s = t % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
})
function _elapsedSince(isoStr) {
  if (!isoStr) return 0
  return Math.max(0, Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000))
}
function startResearchTimer() {
  if (researchElapsedTimer) clearInterval(researchElapsedTimer)
  researchElapsedTimer = setInterval(() => { researchElapsed.value++ }, 1000)
}
function stopResearchTimer() {
  if (researchElapsedTimer) { clearInterval(researchElapsedTimer); researchElapsedTimer = null }
}
const researchEstimatedProgress = computed(() => {
  if (!researchLoading.value) return 0
  const t = researchElapsed.value
  // Slower rise so the indeterminate bar does not sit near 99% for most of a 40 min run
  const pct = Math.round(100 * (1 - Math.exp(-t / 900)))
  return Math.min(Math.max(pct, 1), 99)
})
const showResearchSettings = ref(false)
const researchAngleOverrides = ref({})
const researchCredits = ref(null)
const showBuyResearchModal = ref(false)
const buyingResearch = ref(false)
let typewriterTimer = null

// Session state
const activeSessionId = ref(null)
const activeSessions = ref([])
// Concurrent pollSessionResearch calls share this one ref: one invocation's finally can clear the
// flag while another is still running. If overlapping research polls become possible, use a poll
// instance counter or AbortController per invocation instead.
const researchPollActive = ref(false)
let autoSaveTimer = null
let suppressAutoSave = false
const DRAFT_KEY = 'glas_form_draft'
const SESSION_KEY = 'glas_active_session'

const fullAnalysisMode = ref(false)
const bundlePlan = ref([])
const bundleLoading = ref(false)
const activeBundleId = ref(null)
const scenarioCount = ref(5)
// Tracks whether the user (or a restored session/draft) ever had full-analysis enabled
// in this browser context. Used to warn if they start without it after previously enabling.
const wasFullAnalysisEnabled = ref(false)

onMounted(async () => {
  const full = 'Simulate the future'
  let i = 0
  typewriterTimer = setInterval(() => {
    if (i < full.length) {
      typewriterText.value = full.slice(0, ++i)
    } else {
      typewriterDone.value = true
      clearInterval(typewriterTimer)
      typewriterTimer = null
    }
  }, 70)

  apiGet('/billing/status').then(res => {
    if (res?.success) {
      userPlan.value = normalizeClientPlan(res.data?.plan)
      researchCredits.value = res.data?.research_credits ?? null
    }
  }).catch(() => {
    userPlan.value = 'free'
  })

  if (route.query.prefill) {
    const pending = getPendingUpload()
    if (pending.simulationRequirement) {
      formData.value.simulationRequirement = pending.simulationRequirement
      if (pending.decisionIntake) {
        decisionForm.role = pending.decisionIntake.role || ''
        decisionForm.decision = pending.decisionIntake.decision || ''
        decisionForm.constraints = pending.decisionIntake.constraints || ''
        decisionForm.flip_conditions = pending.decisionIntake.flip_conditions || ''
        prefillRestored.value = true
      }
      clearPendingUpload()
      return
    }
  }

  // Restore from localStorage draft (pre-session convenience)
  try {
    const draft = localStorage.getItem(DRAFT_KEY)
    if (draft) {
      const d = JSON.parse(draft)
      suppressAutoSave = true
      if (d.prompt && !formData.value.simulationRequirement) {
        formData.value.simulationRequirement = d.prompt
      }
      if (d.decision_context) {
        decisionForm.role = d.decision_context.role || ''
        decisionForm.decision = d.decision_context.decision || ''
        decisionForm.constraints = d.decision_context.constraints || ''
        decisionForm.flip_conditions = d.decision_context.flip_conditions || ''
      }
      if (d.full_analysis_mode) {
        fullAnalysisMode.value = true
        wasFullAnalysisEnabled.value = true
        if (Array.isArray(d.bundle_plan)) bundlePlan.value = d.bundle_plan
        if (d.active_bundle_id) activeBundleId.value = d.active_bundle_id
        if (typeof d.scenario_count === 'number') scenarioCount.value = d.scenario_count
      }
      setTimeout(() => { suppressAutoSave = false }, 100)
    }
  } catch { /* ignore corrupt draft */ }

  // Restore active session
  await restoreSession()

  // Fetch sidebar sessions
  loadActiveSessions()

  // Handle return from Stripe research purchase
  if (route.query.auto_research === 'true' && route.query.billing === 'success') {
    const refreshRes = await apiGet('/billing/status').catch(() => null)
    if (refreshRes?.success) researchCredits.value = refreshRes.data?.research_credits ?? 0
    if (activeSessionId.value && researchCredits.value > 0) {
      router.replace({ query: {} })
      runDeepResearch()
    }
  }
})

onUnmounted(() => {
  if (typewriterTimer) clearInterval(typewriterTimer)
  researchPollActive.value = false
  stopResearchTimer()
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
})

const isPaidUser = computed(() => {
  const p = normalizeClientPlan(userPlan.value)
  return ['pro', 'business', 'enterprise', 'payg'].includes(p)
})

const planLimits = computed(() => {
  const p = normalizeClientPlan(userPlan.value)
  if (p === 'business') return { agents: 75, rounds: 30 }
  if (p === 'enterprise') return { agents: 200, rounds: 50 }
  if (p === 'pro' || p === 'payg') return { agents: 50, rounds: 25 }
  return { agents: 25, rounds: 15 }
})

const starterExamples = [
  { icon: '\u{1F3ED}', label: 'US raises tariffs on EU steel by 25%', scenario: 'What happens if the US raises tariffs on EU steel by 25%?' },
  { icon: '\u{1F4CA}', label: 'AI regulation impact on big tech stocks', scenario: 'How will AI regulation affect big tech stock prices over the next 12 months?' },
  { icon: '\u{1F48A}', label: 'Small pharmacy invests in delivery', scenario: 'Should a small independent pharmacy invest in a prescription delivery service?' },
  { icon: '\u{1F3E2}', label: 'Remote work vs commercial real estate', scenario: 'What is the impact of permanent remote work policies on commercial real estate values in major US cities?' },
  { icon: '\u{26A1}', label: 'Energy price cap removal effects', scenario: 'What happens if Ofgem removes the energy price cap in the UK?' },
  { icon: '\u{1F30D}', label: 'EU carbon border tax on manufacturers', scenario: 'How will the EU carbon border adjustment mechanism affect non-EU manufacturers exporting to Europe?' },
]


const canSubmit = computed(() => {
  const hasPrompt = formData.value.simulationRequirement.trim() !== ''
  const hasSources = files.value.length > 0 || briefing.value !== null
  return hasPrompt && hasSources
})

async function handleEnhancePrompt() {
  const prompt = formData.value.simulationRequirement.trim()
  if (!prompt) return
  enhancing.value = true
  try {
    const docNames = files.value.map(f => f.name)
    const res = await apiPost('/graph/enhance-prompt', {
      prompt,
      document_names: docNames,
    })
    if (res?.success && res.enhanced_prompt) {
      formData.value.simulationRequirement = res.enhanced_prompt
    }
  } catch (e) {
    error.value = 'Prompt enhancement failed'
  } finally {
    enhancing.value = false
  }
}

async function runDeepResearch() {
  if (!isPaidUser.value) return
  const prompt = formData.value.simulationRequirement.trim()
  if (!prompt) return

  const isRetry = !!error.value || researchDossier.value === null && activeSessionId.value

  researchLoading.value = true
  error.value = ''
  researchElapsed.value = 0
  researchStatusMessage.value = 'Creating session...'
  startResearchTimer()

  try {
    const sessionId = await ensureSession()

    if (fullAnalysisMode.value && bundlePlan.value.length > 0 && activeBundleId.value) {
      researchStatusMessage.value = 'Saving scenario context...'
      await updateSession(sessionId, {
        bundle_config: {
          bundle_id: activeBundleId.value,
          scenarios: bundlePlan.value,
          full_analysis: true,
        },
      })
    }

    researchStatusMessage.value = 'Starting deep research...'

    const startRes = await startSessionResearch(sessionId, researchAngleOverrides.value)

    if (!startRes?.data) {
      if (startRes?.error === 'no_research_credits') {
        researchLoading.value = false
        stopResearchTimer()
        researchCredits.value = startRes.research_credits ?? 0
        showBuyResearchModal.value = true
        return
      }
      error.value = startRes?.error || 'Failed to start deep research'
      researchLoading.value = false
      stopResearchTimer()
      return
    }

    if (!isRetry && researchCredits.value !== null) researchCredits.value = Math.max(0, researchCredits.value - 1)
    await pollSessionResearch(sessionId)
  } catch (e) {
    // 409 = research already completed — load the existing dossier silently
    if (e?.response?.status === 409 && activeSessionId.value) {
      try {
        const statusRes = await getSessionResearchStatus(activeSessionId.value)
        const dossier = statusRes?.data?.dossier || statusRes?.dossier
        if (dossier?.summary_md) {
          researchDossier.value = dossier
          briefing.value = { title: 'Deep Research Dossier', content_md: dossier.summary_md, filename: 'deep_research_dossier.md' }
          const existing = files.value.findIndex(f => f.name === 'deep_research_dossier.md')
          if (existing !== -1) files.value.splice(existing, 1)
          const blob = new Blob([dossier.summary_md], { type: 'text/markdown' })
          files.value.push(new File([blob], 'deep_research_dossier.md', { type: 'text/markdown' }))
          researchLoading.value = false
          stopResearchTimer()
          return
        }
      } catch (_) { /* fall through to generic error below */ }
    }
    error.value = e?.message || 'Deep research failed. Please refresh and try again.'
    researchLoading.value = false
    stopResearchTimer()
  }
}

async function handleBuyResearch(product) {
  buyingResearch.value = true
  try {
    const res = await buyResearchCredits(product, activeSessionId.value)
    if (res?.success && res.data?.url) {
      window.location.href = res.data.url
    } else {
      error.value = res?.error || 'Failed to start checkout'
      showBuyResearchModal.value = false
    }
  } catch {
    error.value = 'Network error — please try again'
    showBuyResearchModal.value = false
  } finally {
    buyingResearch.value = false
  }
}

function removeBriefing() {
  if (briefing.value) {
    const idx = files.value.findIndex(f => f.name === briefing.value.filename)
    if (idx !== -1) files.value.splice(idx, 1)
    briefing.value = null
  }
}

function onDossierSave(newContent) {
  if (!briefing.value) return
  briefing.value = { ...briefing.value, content_md: newContent }
  if (researchDossier.value) researchDossier.value = { ...researchDossier.value, summary_md: newContent }
  const idx = files.value.findIndex(f => f.name === 'deep_research_dossier.md')
  const blob = new Blob([newContent], { type: 'text/markdown' })
  const updated = new File([blob], 'deep_research_dossier.md', { type: 'text/markdown' })
  if (idx !== -1) files.value.splice(idx, 1, updated)
  else files.value.push(updated)
}

// Used when the dossier came back empty (silent failure). We clear the stale
// dossier from the UI and re-run deep research so the credit-refund / retry
// path in runDeepResearch kicks in cleanly.
function retryEmptyResearch() {
  if (researchLoading.value) return
  removeBriefing()
  researchDossier.value = null
  runDeepResearch()
}

const triggerFileInput = () => { if (!loading.value) fileInput.value?.click() }
const handleFileSelect = (event) => { addFiles(Array.from(event.target.files)) }
const handleDragOver = () => { if (!loading.value) isDragOver.value = true }
const handleDragLeave = () => { isDragOver.value = false }
const handleDrop = (e) => {
  isDragOver.value = false
  if (loading.value) return
  addFiles(Array.from(e.dataTransfer.files))
}
const addFiles = (newFiles) => {
  const validFiles = newFiles.filter(file => {
    const ext = file.name.split('.').pop().toLowerCase()
    return ['pdf', 'md', 'txt', 'markdown'].includes(ext)
  })
  files.value.push(...validFiles)
}
const removeFile = (index) => { files.value.splice(index, 1) }
function openFile(file) {
  const url = URL.createObjectURL(file)
  window.open(url, '_blank')
}
const scrollToBottom = () => { window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }) }

// ── Session helpers ──

async function loadActiveSessions() {
  try {
    const res = await getActiveSessions()
    if (res?.data) activeSessions.value = res.data
  } catch (err) {
    console.warn('load active sessions', err)
  }
}

async function restoreSession() {
  const savedId = localStorage.getItem(SESSION_KEY)
  if (!savedId) return

  suppressAutoSave = true
  try {
    const res = await getSession(savedId)
    if (!res?.data) {
      localStorage.removeItem(SESSION_KEY)
      return
    }
    const s = res.data
    if (s.status === 'completed' || s.status === 'abandoned') {
      localStorage.removeItem(SESSION_KEY)
      return
    }

    activeSessionId.value = s.id
    formData.value.simulationRequirement = s.prompt || ''

    const dc = s.decision_context || {}
    decisionForm.role = dc.role || ''
    decisionForm.decision = dc.decision || ''
    decisionForm.constraints = dc.constraints || ''
    decisionForm.flip_conditions = dc.flip_conditions || ''

    const bc = s.bundle_config
    if (bc && typeof bc === 'object' && bc.full_analysis) {
      fullAnalysisMode.value = true
      wasFullAnalysisEnabled.value = true
      activeBundleId.value = bc.bundle_id || null
      bundlePlan.value = Array.isArray(bc.scenarios) ? bc.scenarios : []
      if (bundlePlan.value.length) scenarioCount.value = bundlePlan.value.length
    }

    if (s.research_status === 'completed' && s.research_dossier) {
      researchDossier.value = s.research_dossier
      briefing.value = {
        title: 'Deep Research Dossier',
        content_md: s.research_dossier.summary_md || '',
        filename: 'deep_research_dossier.md',
      }
      if (s.research_dossier.summary_md) {
        const blob = new Blob([s.research_dossier.summary_md], { type: 'text/markdown' })
        const existing = files.value.findIndex(f => f.name === 'deep_research_dossier.md')
        if (existing === -1) {
          files.value.push(new File([blob], 'deep_research_dossier.md', { type: 'text/markdown' }))
        }
      }
    } else if (s.research_status === 'processing' || s.research_status === 'queued' || s.research_status === 'claiming') {
      researchLoading.value = true
      researchElapsed.value = _elapsedSince(s.research_started_at)
      researchStatusMessage.value = 'Resuming research...'
      startResearchTimer()
      pollSessionResearch(s.id)
    }

    localStorage.removeItem(DRAFT_KEY)
  } catch {
    localStorage.removeItem(SESSION_KEY)
  } finally {
    setTimeout(() => { suppressAutoSave = false }, 100)
  }
}

async function restoreFromSession(session) {
  suppressAutoSave = true
  activeSessionId.value = session.id
  localStorage.setItem(SESSION_KEY, session.id)
  formData.value.simulationRequirement = session.prompt || ''
  const dc = session.decision_context || {}
  decisionForm.role = dc.role || ''
  decisionForm.decision = dc.decision || ''
  decisionForm.constraints = dc.constraints || ''
  decisionForm.flip_conditions = dc.flip_conditions || ''

  const bc = session.bundle_config
  if (bc && typeof bc === 'object' && bc.full_analysis) {
    fullAnalysisMode.value = true
    wasFullAnalysisEnabled.value = true
    activeBundleId.value = bc.bundle_id || null
    bundlePlan.value = bc.scenarios || []
    scenarioCount.value = bundlePlan.value.length || 5
  } else {
    fullAnalysisMode.value = false
    wasFullAnalysisEnabled.value = false
    activeBundleId.value = null
    bundlePlan.value = []
  }

  let fullSession = session
  if (session.research_status === 'completed' && !session.research_dossier) {
    try {
      const res = await getSession(session.id)
      if (res?.data) fullSession = res.data
    } catch { /* use sidebar data as fallback */ }
  }

  if (fullSession.research_status === 'completed' && fullSession.research_dossier) {
    researchDossier.value = fullSession.research_dossier
    briefing.value = {
      title: 'Deep Research Dossier',
      content_md: fullSession.research_dossier.summary_md || '',
      filename: 'deep_research_dossier.md',
    }
    if (fullSession.research_dossier.summary_md) {
      const blob = new Blob([fullSession.research_dossier.summary_md], { type: 'text/markdown' })
      const existing = files.value.findIndex(f => f.name === 'deep_research_dossier.md')
      if (existing === -1) {
        files.value.push(new File([blob], 'deep_research_dossier.md', { type: 'text/markdown' }))
      }
    }
  } else if (fullSession.research_status === 'processing' || fullSession.research_status === 'queued' || fullSession.research_status === 'claiming') {
    researchLoading.value = true
    researchElapsed.value = _elapsedSince(fullSession.research_started_at)
    researchStatusMessage.value = 'Resuming research...'
    startResearchTimer()
    pollSessionResearch(fullSession.id)
    setTimeout(() => { suppressAutoSave = false }, 100)
    return
  }

  const navStatus = ['simulating', 'completed', 'sim_failed']
  const bundleId = bc?.bundle_id
  if (navStatus.includes(fullSession.status) && bundleId) {
    router.push({ name: 'BundleResults', params: { bundleId } })
    return
  }
  if (navStatus.includes(fullSession.status) && fullSession.simulation_id) {
    router.push({ name: 'SimulationRun', params: { simulationId: fullSession.simulation_id } })
    return
  }
  if (fullSession.project_id) {
    router.push({ name: 'Process', params: { projectId: fullSession.project_id }, query: { session_id: fullSession.id } })
    return
  }

  setTimeout(() => { suppressAutoSave = false }, 100)
}

async function handleAbandonSession(sessionId) {
  try {
    await abandonSession(sessionId)
    activeSessions.value = activeSessions.value.filter(s => s.id !== sessionId)
    if (activeSessionId.value === sessionId) {
      activeSessionId.value = null
      localStorage.removeItem(SESSION_KEY)
      wasFullAnalysisEnabled.value = false
    }
  } catch { /* ignore */ }
}

async function ensureSession() {
  if (activeSessionId.value) return activeSessionId.value

  const prompt = formData.value.simulationRequirement.trim()
  const dc = { ...decisionForm }
  const res = await createSession(prompt, dc)
  if (!res?.data?.id) throw new Error(res?.error || 'Failed to create session')

  activeSessionId.value = res.data.id
  localStorage.setItem(SESSION_KEY, res.data.id)
  localStorage.removeItem(DRAFT_KEY)

  if (files.value.length > 0) {
    const fd = new FormData()
    files.value.forEach((f, i) => fd.append(`file_${i}`, f))
    try {
      await uploadSessionFiles(res.data.id, fd)
    } catch (err) {
      console.warn('file upload to session', err)
    }
  }

  loadActiveSessions()
  return res.data.id
}

async function pollSessionResearch(sessionId) {
  researchPollActive.value = true
  try {
    let pollFailures = 0
    const BASE_POLL_MS = 4000
    while (true) {
      if (!researchPollActive.value) {
        researchLoading.value = false
        stopResearchTimer()
        return
      }
      const delay = pollFailures > 0 ? Math.min(BASE_POLL_MS * Math.pow(2, pollFailures), 30000) : BASE_POLL_MS
      await new Promise(r => setTimeout(r, delay))
      if (!researchPollActive.value) {
        researchLoading.value = false
        stopResearchTimer()
        return
      }
      let statusRes
      try {
        statusRes = await getSessionResearchStatus(sessionId)
      } catch (err) {
        const is401 = err?.response?.status === 401 || err?.message?.includes('JWT')
        if (is401 && pollFailures === 0) {
          try { await refreshAccessToken() } catch { /* best effort */ }
        }
        pollFailures++
        if (pollFailures >= 8) {
          error.value = 'Lost connection to research task. Please refresh and try again.'
          researchLoading.value = false
          stopResearchTimer()
          return
        }
        researchStatusMessage.value = `Reconnecting... (attempt ${pollFailures}/8)`
        continue
      }
      if (pollFailures > 0) researchStatusMessage.value = 'Reconnected — research in progress...'
      pollFailures = 0

      const data = statusRes.data
      researchStatusMessage.value = data.message || 'Research in progress...'

      if (data.status === 'completed') {
        const dossier = data.dossier
        researchDossier.value = dossier
        briefing.value = {
          title: 'Deep Research Dossier',
          content_md: dossier?.summary_md || '',
          filename: 'deep_research_dossier.md',
        }
        if (dossier?.summary_md) {
          const existing = files.value.findIndex(f => f.name === 'deep_research_dossier.md')
          if (existing !== -1) files.value.splice(existing, 1)
          const blob = new Blob([dossier.summary_md], { type: 'text/markdown' })
          files.value.push(new File([blob], 'deep_research_dossier.md', { type: 'text/markdown' }))
        }
        researchLoading.value = false
        stopResearchTimer()
        return
      }

      if (data.status === 'failed') {
        error.value = data.message || 'Deep research failed'
        researchLoading.value = false
        stopResearchTimer()
        apiGet('/billing/status').then(res => {
          if (res?.success) researchCredits.value = res.data?.research_credits ?? researchCredits.value
        }).catch(() => {})
        return
      }
    }
  } finally {
    researchPollActive.value = false
  }
}

// Auto-save draft to localStorage (pre-session)
function saveDraft() {
  if (suppressAutoSave || activeSessionId.value) return
  const draft = {
    prompt: formData.value.simulationRequirement,
    decision_context: { ...decisionForm },
    full_analysis_mode: fullAnalysisMode.value,
    bundle_plan: bundlePlan.value,
    active_bundle_id: activeBundleId.value,
    scenario_count: scenarioCount.value,
  }
  try { localStorage.setItem(DRAFT_KEY, JSON.stringify(draft)) } catch { /* quota */ }
}

// Auto-save to session API (post-session)
function scheduleSessionSave() {
  if (suppressAutoSave || !activeSessionId.value) return
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(async () => {
    try {
      const fields = {
        prompt: formData.value.simulationRequirement,
        decision_context: { ...decisionForm },
        // Always send bundle_config so toggling off persists; null clears it server-side.
        bundle_config: fullAnalysisMode.value
          ? {
              bundle_id: activeBundleId.value,
              scenarios: bundlePlan.value,
              full_analysis: true,
            }
          : null,
      }
      await updateSession(activeSessionId.value, fields)
    } catch (err) {
      console.warn('autosave session', err)
    }
  }, 2000)
}

watch(() => formData.value.simulationRequirement, () => {
  if (fullAnalysisMode.value) {
    fullAnalysisMode.value = false
  }
  saveDraft()
  scheduleSessionSave()
})

watch(decisionForm, () => {
  if (prefillRestored.value) prefillRestored.value = false
  saveDraft()
  scheduleSessionSave()
}, { deep: true })

watch(fullAnalysisMode, (enabled) => {
  if (enabled) {
    wasFullAnalysisEnabled.value = true
  } else {
    bundlePlan.value = []
    activeBundleId.value = null
  }
  saveDraft()
  scheduleSessionSave()
})

watch(bundlePlan, () => {
  scheduleSessionSave()
}, { deep: true })

async function generateScenarios() {
  const prompt = formData.value.simulationRequirement.trim()
  if (!prompt) return
  bundleLoading.value = true
  try {
    const res = await createBundle({
      title: prompt.slice(0, 100),
      decision_context: prompt,
      scenario_count: scenarioCount.value,
    })
    if (!fullAnalysisMode.value) return
    if (res.data) {
      activeBundleId.value = res.data.id
      bundlePlan.value = res.data.suggested_scenarios || []
      trackEvent('bundle_created', { scenario_count: bundlePlan.value.length })
    }
  } catch (e) {
    console.error('Bundle creation failed:', e)
    error.value = 'Failed to generate scenarios. Please try again.'
  } finally {
    bundleLoading.value = false
  }
}

function addScenario() {
  if (bundlePlan.value.length >= 7) return
  bundlePlan.value.push({
    title: `Scenario ${bundlePlan.value.length + 1}`,
    scenario: '',
    change_summary: 'Custom scenario',
  })
}

function removeScenario(index) {
  if (bundlePlan.value.length <= 2) return
  bundlePlan.value.splice(index, 1)
}

const startSimulation = async () => {
  if (!canSubmit.value || loading.value) return
  if (!isPaidUser.value) {
    showUpgradeModal.value = true
    return
  }
  if (fullAnalysisMode.value && (!activeBundleId.value || bundlePlan.value.length === 0)) {
    error.value = 'Generate scenarios first before starting full analysis.'
    return
  }
  // Guard: user previously enabled Full Decision Analysis but it's currently off.
  // This catches the case where a refresh / accidental toggle would silently
  // start a single-scenario run when they intended a multi-scenario one.
  if (!fullAnalysisMode.value && wasFullAnalysisEnabled.value) {
    const ok = window.confirm(
      'Full Decision Analysis is currently OFF, but you had it enabled earlier. ' +
      'Start a single-scenario analysis instead? Click Cancel to re-enable it.'
    )
    if (!ok) return
  }

  loading.value = true
  error.value = ''

  try {
    const sessionId = await ensureSession()

    const hasDecision = decisionForm.role || decisionForm.decision
    const intake = hasDecision ? { ...decisionForm } : null

    if (fullAnalysisMode.value && activeBundleId.value && bundlePlan.value.length > 0) {
      await updateSession(sessionId, {
        bundle_config: {
          bundle_id: activeBundleId.value,
          scenarios: bundlePlan.value,
          full_analysis: true,
        },
      })
      await updateBundle(activeBundleId.value, { suggested_scenarios: bundlePlan.value })

      setPendingUpload(files.value, formData.value.simulationRequirement, intake, researchDossier.value, {
        bundleId: activeBundleId.value,
        scenarios: bundlePlan.value,
      })
    } else {
      setPendingUpload(files.value, formData.value.simulationRequirement, intake, researchDossier.value)
    }

    localStorage.removeItem(DRAFT_KEY)

    router.push({ name: 'Process', params: { projectId: 'new' }, query: { session_id: sessionId } })
  } catch (e) {
    error.value = e?.message || 'Failed to start session'
  } finally {
    loading.value = false
  }
}

function sessionStatusLabel(s) {
  if (s.research_status === 'failed') return 'Research Failed'
  if (s.research_status === 'queued') return 'Research Queued'
  if (s.research_status === 'claiming') return 'Research Starting'
  if (s.research_status === 'processing') return 'Researching'
  if (s.status === 'research_complete') return 'Research Done'

  const bc = s.bundle_config
  if (bc && typeof bc === 'object' && bc.full_analysis) {
    if (s.status === 'simulating') {
      return 'Running Analysis'
    }
    if (s.status === 'completed') return 'Analysis Complete'
    if (s.status === 'sim_failed') return 'Analysis Failed'
  }

  if (s.status === 'simulating') return 'Simulating'
  if (s.status === 'sim_failed') return 'Simulation Failed'
  if (s.status === 'completed') return 'Completed'
  return 'Active'
}

function timeAgo(isoStr) {
  if (!isoStr) return ''
  const diff = Date.now() - new Date(isoStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}
</script>

<style scoped src="./Home.scoped.css"></style>
