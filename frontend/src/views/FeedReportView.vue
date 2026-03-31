<template>
  <div class="report-page">
    <AppNavbar />

    <div v-if="!report" class="loading-state">
      <div class="spinner"></div>
      <span>Loading report...</span>
    </div>

    <article v-else class="report-content">
      <header class="report-header">
        <router-link to="/feed" class="back-link">&larr; Back to Feed</router-link>
        <span class="industry-badge" :class="badgeClass">{{ report.industry }}</span>
        <h1 class="report-title">{{ report.title }}</h1>
        <div class="report-meta">
          <span class="meta-date">{{ report.date }}</span>
          <span class="meta-sep">&middot;</span>
          <span class="meta-read">{{ report.readTime }} min read</span>
          <span v-if="report.access === 'full'" class="meta-free">Full Report</span>
        </div>
        <p class="report-scenario">
          <strong>Scenario:</strong> {{ report.scenario }}
        </p>
      </header>

      <div class="report-body" v-html="report.bodyHtml"></div>

      <div class="report-cta">
        <div class="cta-inner">
          <h3>Want custom scenario analysis?</h3>
          <p>Run your own multi-agent simulations with Glas Intelligence. Try a free simulation or subscribe for full access.</p>
          <div class="cta-actions">
            <router-link to="/pricing" class="cta-btn cta-btn--primary">View Plans</router-link>
            <router-link to="/" class="cta-btn cta-btn--secondary">Try a Simulation</router-link>
          </div>
        </div>
      </div>
    </article>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppNavbar from '../components/AppNavbar.vue'
import { useApi } from '../composables/useApi'
import DOMPurify from 'dompurify'

const { apiGet } = useApi()
const route = useRoute()
const router = useRouter()
const report = ref(null)
const badgeClass = ref('')

const demoReports = {
  'demo-iran': {
    title: 'US-Iran Nuclear Conflict: 9-Scenario Impact Analysis',
    industry: 'Geopolitics',
    date: 'Jan 30, 2026',
    readTime: 12,
    access: 'free',
    scenario: 'Targeted military strikes on Iran\'s nuclear facilities at Natanz and Fordow following collapsed diplomatic channels.',
    badgeClass: 'badge-geopolitics',
    bodyHtml: `
      <h2>Executive Summary</h2>
      <p>This multi-agent simulation models the consequences of nine distinct policy scenarios regarding the US-Iran nuclear confrontation. Using 38 stakeholder agents representing governments, military leaders, economic institutions, and civilian populations, the simulation evaluates each scenario across five key dimensions over an 18-month horizon.</p>

      <div class="key-finding">
        <strong>Key Finding:</strong> The Negotiated Deal (JCPOA 2.0) scenario achieves the highest composite score of <span class="score positive">+8.0</span>, while Full Military Conflict scores the lowest at <span class="score negative">-12.6</span>.
      </div>

      <h2>Scenarios Analysed</h2>
      <div class="scenario-table">
        <div class="scenario-row header">
          <span class="scenario-name">Scenario</span>
          <span class="scenario-score">Score</span>
          <span class="scenario-risk">Risk Level</span>
        </div>
        <div class="scenario-row">
          <span class="scenario-name">1. Negotiated Deal (JCPOA 2.0)</span>
          <span class="scenario-score positive">+8.0</span>
          <span class="scenario-risk low">Low</span>
        </div>
        <div class="scenario-row">
          <span class="scenario-name">2. Enhanced Sanctions Only</span>
          <span class="scenario-score neutral">+2.1</span>
          <span class="scenario-risk medium">Medium</span>
        </div>
        <div class="scenario-row">
          <span class="scenario-name">3. Covert Operations (Stuxnet 2.0)</span>
          <span class="scenario-score neutral">+1.4</span>
          <span class="scenario-risk medium">Medium</span>
        </div>
        <div class="scenario-row">
          <span class="scenario-name">4. Limited Strikes (Natanz Only)</span>
          <span class="scenario-score negative">-3.2</span>
          <span class="scenario-risk high">High</span>
        </div>
        <div class="scenario-row">
          <span class="scenario-name">5. Targeted Strikes (Multiple Sites)</span>
          <span class="scenario-score negative">-5.8</span>
          <span class="scenario-risk high">High</span>
        </div>
        <div class="scenario-row">
          <span class="scenario-name">6. Air Campaign + Cyber</span>
          <span class="scenario-score negative">-7.4</span>
          <span class="scenario-risk critical">Critical</span>
        </div>
        <div class="scenario-row">
          <span class="scenario-name">7. Coalition Strikes</span>
          <span class="scenario-score negative">-6.1</span>
          <span class="scenario-risk high">High</span>
        </div>
        <div class="scenario-row">
          <span class="scenario-name">8. Naval Blockade + Strikes</span>
          <span class="scenario-score negative">-9.3</span>
          <span class="scenario-risk critical">Critical</span>
        </div>
        <div class="scenario-row">
          <span class="scenario-name">9. Full Military Conflict</span>
          <span class="scenario-score negative">-12.6</span>
          <span class="scenario-risk critical">Critical</span>
        </div>
      </div>

      <h2>Five Dimensions of Analysis</h2>
      <p>Each scenario was scored across five dimensions on a scale of -20 to +20:</p>

      <h3>1. Economic Sustainability</h3>
      <p>Measures the impact on global oil markets, trade routes, sanctions regimes, and regional economic stability. The negotiated deal scenario projects oil price stabilisation within 3 months, while full conflict models a 40-65% spike in crude prices sustained over 12+ months with cascading effects on global supply chains.</p>

      <h3>2. Social Cohesion</h3>
      <p>Evaluates domestic and regional social stability, refugee flows, sectarian tensions, and public sentiment. Military scenarios consistently trigger increased social fragmentation, with the full conflict scenario projecting 2-4 million displaced persons and significant humanitarian crises across Iraq, Lebanon, and the Gulf states.</p>

      <h3>3. State Capacity</h3>
      <p>Assesses the ability of affected states to maintain governance, infrastructure, and institutional function. Even limited strikes reduce Iranian state capacity by an estimated 15-25%, while full conflict scenarios model near-complete institutional paralysis in the first 6 months.</p>

      <h3>4. Long-term Resilience</h3>
      <p>Projects the 5-10 year outlook for regional stability and recovery capacity. Diplomatic scenarios show the strongest long-term trajectory, with nuclear verification frameworks providing durable stability. Military scenarios uniformly degrade long-term resilience, with the most severe options creating conditions for prolonged instability and potential state failure.</p>

      <h3>5. Democratic Legitimacy</h3>
      <p>Examines effects on democratic institutions, civil liberties, and political accountability across the region. Negotiated outcomes strengthen reformist movements within Iran, while military action consistently empowers hardline factions and justifies authoritarian consolidation.</p>

      <h2>Stakeholder Dynamics</h2>
      <p>The simulation modelled 38 distinct stakeholder agents across 6 categories:</p>
      <ul>
        <li><strong>Government actors</strong> (12 agents): US administration, Iranian leadership, EU foreign policy, Russian and Chinese diplomatic positions, Gulf state governments</li>
        <li><strong>Military/security</strong> (8 agents): IRGC, US Central Command, Israeli defence establishment, NATO partners</li>
        <li><strong>Economic institutions</strong> (6 agents): OPEC, central banks, major energy companies, shipping/insurance markets</li>
        <li><strong>International organisations</strong> (4 agents): IAEA, UN Security Council, International Court of Justice</li>
        <li><strong>Civil society</strong> (5 agents): Iranian civilian population, regional diaspora communities, international media</li>
        <li><strong>Non-state actors</strong> (3 agents): Hezbollah, Houthi forces, Iraqi militias</li>
      </ul>

      <h2>Confidence Assessment</h2>
      <p>Overall simulation confidence ranges from <strong>72% to 85%</strong> depending on scenario complexity. Diplomatic scenarios carry higher confidence (82-85%) due to historical precedent from JCPOA negotiations. Military scenarios carry lower confidence (72-78%) due to higher uncertainty in escalation dynamics and second-order effects.</p>

      <div class="key-finding">
        <strong>Recommendation:</strong> The simulation strongly favours renewed diplomatic engagement. Every military scenario produces net-negative outcomes across all five dimensions. The optimal path combines a JCPOA 2.0 framework with enhanced verification mechanisms and phased sanctions relief, achieving the best composite score while maintaining credible deterrence.
      </div>

      <h2>Methodology</h2>
      <p>This analysis was generated using the Glas Intelligence multi-agent simulation engine. Stakeholder agents were configured with LLM-driven personas based on publicly available policy positions, historical behaviour patterns, and institutional incentive structures. The simulation ran 15 rounds of interaction across all nine scenarios, with agents adapting their positions based on observed outcomes and counterpart responses.</p>
      <p>Source materials included academic papers on nuclear deterrence theory, IAEA inspection reports, Congressional Research Service analyses, and regional stability assessments from major think tanks.</p>
    `,
  },
}

onMounted(async () => {
  const id = route.params.id
  const demo = demoReports[id]
  if (demo) {
    report.value = demo
    badgeClass.value = demo.badgeClass
    return
  }

  try {
    const res = await apiGet(`/feed/simulations/${id}`)
    if (res.success && res.data) {
      const item = res.data
      report.value = {
        title: item.title || 'Untitled Report',
        industry: item.industry || 'General',
        date: item.published_at ? new Date(item.published_at).toLocaleDateString('en-GB', { year: 'numeric', month: 'long', day: 'numeric' }) : '',
        readTime: item.read_time || 12,
        scenario: item.scenario_description || '',
        access: item.access || 'summary',
        bodyHtml: DOMPurify.sanitize(item.report_html || item.summary || ''),
      }
      badgeClass.value = 'badge-general'
    } else {
      router.replace('/feed')
    }
  } catch {
    router.replace('/feed')
  }
})
</script>

<style scoped>
.report-page {
  min-height: 100vh;
  background: #0a0a0a;
  color: #e0e0e0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 120px 0;
  color: #666;
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #333;
  border-top-color: #4ade80;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.report-content {
  max-width: 780px;
  margin: 0 auto;
  padding: 48px 40px 120px;
}

.back-link {
  display: inline-block;
  color: #888;
  text-decoration: none;
  font-size: 0.85rem;
  margin-bottom: 32px;
  transition: color 0.2s;
}

.back-link:hover {
  color: #4ade80;
}

.industry-badge {
  display: inline-block;
  font-size: 0.7rem;
  font-weight: 600;
  padding: 4px 10px;
  margin-bottom: 16px;
  letter-spacing: 0.5px;
}

.badge-geopolitics {
  background: rgba(248, 113, 113, 0.1);
  color: #f87171;
  border: 1px solid rgba(248, 113, 113, 0.2);
}

.badge-energy {
  background: rgba(74, 222, 128, 0.1);
  color: #4ade80;
  border: 1px solid rgba(74, 222, 128, 0.2);
}

.badge-finance {
  background: rgba(96, 165, 250, 0.1);
  color: #60a5fa;
  border: 1px solid rgba(96, 165, 250, 0.2);
}

.report-title {
  font-size: 2.4rem;
  font-weight: 700;
  line-height: 1.2;
  margin: 0 0 20px 0;
  letter-spacing: -0.02em;
  color: #f0f0f0;
}

.report-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.85rem;
  color: #666;
  margin-bottom: 24px;
}

.meta-sep {
  color: #333;
}

.meta-free {
  background: rgba(74, 222, 128, 0.1);
  color: #4ade80;
  border: 1px solid rgba(74, 222, 128, 0.2);
  padding: 2px 8px;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.report-scenario {
  color: #888;
  font-size: 1rem;
  line-height: 1.6;
  padding: 16px 20px;
  border-left: 3px solid #FF6B35;
  background: rgba(255, 107, 53, 0.05);
  margin: 0 0 48px 0;
}

.report-scenario strong {
  color: #bbb;
}

.report-body {
  line-height: 1.8;
  font-size: 1.02rem;
}

.report-body :deep(h2) {
  font-size: 1.5rem;
  font-weight: 700;
  color: #f0f0f0;
  margin: 48px 0 16px 0;
  padding-bottom: 10px;
  border-bottom: 1px solid #1e1e1e;
}

.report-body :deep(h3) {
  font-size: 1.15rem;
  font-weight: 600;
  color: #e0e0e0;
  margin: 32px 0 12px 0;
}

.report-body :deep(p) {
  color: #bbb;
  margin: 0 0 16px 0;
}

.report-body :deep(ul) {
  padding-left: 20px;
  margin: 0 0 20px 0;
}

.report-body :deep(li) {
  color: #bbb;
  margin-bottom: 8px;
  line-height: 1.7;
}

.report-body :deep(li strong) {
  color: #e0e0e0;
}

.report-body :deep(.key-finding) {
  padding: 20px 24px;
  background: rgba(74, 222, 128, 0.05);
  border: 1px solid rgba(74, 222, 128, 0.15);
  border-left: 3px solid #4ade80;
  margin: 24px 0;
  color: #ccc;
  line-height: 1.7;
}

.report-body :deep(.key-finding strong) {
  color: #4ade80;
}

.report-body :deep(.score) {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
}

.report-body :deep(.score.positive) {
  color: #4ade80;
}

.report-body :deep(.score.negative) {
  color: #f87171;
}

.report-body :deep(.scenario-table) {
  margin: 20px 0 32px;
  border: 1px solid #2a2a2a;
}

.report-body :deep(.scenario-row) {
  display: grid;
  grid-template-columns: 1fr 80px 90px;
  padding: 12px 16px;
  border-bottom: 1px solid #1e1e1e;
  font-size: 0.9rem;
  align-items: center;
}

.report-body :deep(.scenario-row:last-child) {
  border-bottom: none;
}

.report-body :deep(.scenario-row.header) {
  background: #111;
  font-weight: 600;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: #888;
}

.report-body :deep(.scenario-name) {
  color: #ccc;
}

.report-body :deep(.scenario-score) {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  text-align: center;
}

.report-body :deep(.scenario-score.positive) {
  color: #4ade80;
}

.report-body :deep(.scenario-score.neutral) {
  color: #fbbf24;
}

.report-body :deep(.scenario-score.negative) {
  color: #f87171;
}

.report-body :deep(.scenario-risk) {
  text-align: center;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 2px;
}

.report-body :deep(.scenario-risk.low) {
  color: #4ade80;
  background: rgba(74, 222, 128, 0.1);
}

.report-body :deep(.scenario-risk.medium) {
  color: #fbbf24;
  background: rgba(251, 191, 36, 0.1);
}

.report-body :deep(.scenario-risk.high) {
  color: #fb923c;
  background: rgba(251, 146, 60, 0.1);
}

.report-body :deep(.scenario-risk.critical) {
  color: #f87171;
  background: rgba(248, 113, 113, 0.1);
}

.report-cta {
  margin-top: 64px;
  padding-top: 48px;
  border-top: 1px solid #1e1e1e;
}

.cta-inner {
  text-align: center;
  padding: 40px;
  border: 1px solid #2a2a2a;
  background: #111;
}

.cta-inner h3 {
  font-size: 1.4rem;
  font-weight: 700;
  color: #f0f0f0;
  margin: 0 0 12px 0;
}

.cta-inner p {
  color: #888;
  margin: 0 0 28px 0;
  line-height: 1.6;
  max-width: 480px;
  margin-left: auto;
  margin-right: auto;
}

.cta-actions {
  display: flex;
  gap: 16px;
  justify-content: center;
}

.cta-btn {
  padding: 14px 28px;
  font-size: 0.85rem;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-decoration: none;
  transition: all 0.2s;
  cursor: pointer;
  border: none;
}

.cta-btn--primary {
  background: #4ade80;
  color: #000;
}

.cta-btn--primary:hover {
  background: #22c55e;
}

.cta-btn--secondary {
  background: transparent;
  border: 1px solid #333;
  color: #ccc;
}

.cta-btn--secondary:hover {
  border-color: #666;
  color: #fff;
}

@media (max-width: 768px) {
  .report-content {
    padding: 32px 20px 80px;
  }

  .report-title {
    font-size: 1.8rem;
  }

  .report-body :deep(.scenario-row) {
    grid-template-columns: 1fr 60px 70px;
    font-size: 0.8rem;
    padding: 10px 12px;
  }

  .cta-actions {
    flex-direction: column;
  }
}
</style>
