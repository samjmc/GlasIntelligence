<template>
  <div class="report-panel">
    <!-- Main Split Layout -->
    <div class="main-split-layout">
      <!-- LEFT PANEL: Report Style -->
      <div class="left-panel report-style" ref="leftPanel">
        <div v-if="reportOutline" class="report-content-wrapper">
          <!-- Report Header -->
          <div class="report-header-block">
            <div class="report-meta">
              <span class="report-tag">Prediction Report</span>
              <span class="report-id">ID: {{ reportId || 'REF-2024-X92' }}</span>
            </div>
            <h1 class="main-title">{{ reportOutline.title }}</h1>
            <p class="sub-title">{{ reportOutline.summary }}</p>
            <p v-if="isComplete" class="report-disclaimer">
              Probabilities and risk scores are simulation-derived, not investment advice.
            </p>
            <div class="header-divider"></div>
          </div>

          <!-- Decision Recommendation (from payload, shown after report completes) -->
          <div v-if="isComplete && decisionPayload" class="decision-recommendation-card">
            <div class="decision-card-header">
              <span class="section-number">DR</span>
              <h3 class="section-title">Decision Recommendation</h3>
            </div>
            <div class="decision-card-body">
              <div class="verdict-row">
                <span class="verdict-label">Verdict</span>
                <span class="verdict-value" :class="verdictClass">{{ decisionPayload.verdict }}</span>
                <span class="confidence-badge" :class="'conf-' + (decisionPayload.confidence || 'low')">
                  <span class="conf-dots">
                    <span class="conf-dot filled"></span>
                    <span class="conf-dot" :class="{ filled: decisionPayload.confidence !== 'low' }"></span>
                    <span class="conf-dot" :class="{ filled: decisionPayload.confidence === 'high' }"></span>
                  </span>
                  {{ decisionPayload.confidence }} confidence
                </span>
              </div>
              <p class="verdict-reasoning">{{ decisionPayload.reasoning }}</p>
              <p v-if="decisionPayload.confidence_rationale" class="confidence-rationale">{{ decisionPayload.confidence_rationale }}</p>

              <div v-if="decisionPayload.key_drivers?.length" class="decision-section">
                <h4>Key Drivers</h4>
                <table class="decision-table">
                  <thead><tr><th>Driver</th><th>Direction</th><th>Magnitude</th></tr></thead>
                  <tbody>
                    <tr v-for="(d, i) in decisionPayload.key_drivers" :key="i">
                      <td>{{ d.name }}</td>
                      <td :class="'dir-' + d.direction">{{ d.direction }}</td>
                      <td>{{ d.magnitude }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div v-if="decisionPayload.causal_chain?.length" class="decision-section causal-section">
                <h4>Why This Makes Sense</h4>
                <div class="causal-chain">
                  <div v-for="(link, i) in decisionPayload.causal_chain" :key="i" class="causal-link">
                    <div class="causal-node cause-node">
                      <span class="causal-text">{{ link.cause }}</span>
                    </div>
                    <div class="causal-arrow">
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/></svg>
                    </div>
                    <div class="causal-node effect-node">
                      <span class="causal-text">{{ link.effect }}</span>
                      <span v-if="link.confidence" class="causal-conf" :class="'conf-' + link.confidence">{{ link.confidence }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div v-if="decisionPayload.sensitivity?.length" class="decision-section">
                <h4>Sensitivity Analysis</h4>
                <table class="decision-table">
                  <thead><tr><th>Variable</th><th>Base</th><th>Swing</th><th>Impact</th></tr></thead>
                  <tbody>
                    <tr v-for="(s, i) in decisionPayload.sensitivity" :key="i">
                      <td>{{ s.variable }}</td>
                      <td>{{ s.base_value }}</td>
                      <td>{{ s.swing_pct }}</td>
                      <td>{{ s.impact_on_verdict }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div v-if="decisionPayload.flip_conditions?.length" class="decision-section">
                <h4>Flip Conditions</h4>
                <ul class="flip-list">
                  <li v-for="(fc, i) in decisionPayload.flip_conditions" :key="i">{{ fc }}</li>
                </ul>
              </div>

              <div v-if="decisionPayload.financial_summary?.applicable" class="decision-section financial-section">
                <h4>Financial Estimates</h4>
                <table class="decision-table financial-table">
                  <thead><tr><th>Metric</th><th>Low</th><th>High</th><th>Unit</th></tr></thead>
                  <tbody>
                    <tr v-if="decisionPayload.financial_summary.revenue_range">
                      <td>Revenue</td>
                      <td>{{ decisionPayload.financial_summary.revenue_range.low }}</td>
                      <td>{{ decisionPayload.financial_summary.revenue_range.high }}</td>
                      <td>{{ decisionPayload.financial_summary.revenue_range.unit }}</td>
                    </tr>
                    <tr v-if="decisionPayload.financial_summary.cost_range">
                      <td>Costs</td>
                      <td>{{ decisionPayload.financial_summary.cost_range.low }}</td>
                      <td>{{ decisionPayload.financial_summary.cost_range.high }}</td>
                      <td>{{ decisionPayload.financial_summary.cost_range.unit }}</td>
                    </tr>
                    <tr v-if="decisionPayload.financial_summary.profit_range">
                      <td>Profit</td>
                      <td class="profit-low">{{ decisionPayload.financial_summary.profit_range.low }}</td>
                      <td class="profit-high">{{ decisionPayload.financial_summary.profit_range.high }}</td>
                      <td>{{ decisionPayload.financial_summary.profit_range.unit }}</td>
                    </tr>
                  </tbody>
                </table>
                <div class="financial-meta">
                  <span v-if="decisionPayload.financial_summary.break_even" class="financial-tag">Break-even: {{ decisionPayload.financial_summary.break_even }}</span>
                  <span v-if="decisionPayload.financial_summary.time_horizon" class="financial-tag">Horizon: {{ decisionPayload.financial_summary.time_horizon }}</span>
                </div>
              </div>

              <div v-if="decisionPayload.recommended_actions?.length" class="decision-section action-plan-section">
                <h4>Recommended Actions</h4>
                <div class="action-plan-list">
                  <div v-for="(a, i) in decisionPayload.recommended_actions" :key="i" class="action-plan-item" :class="'priority-' + a.priority">
                    <div class="action-plan-header">
                      <span class="action-priority-badge" :class="'priority-' + a.priority">{{ a.priority }}</span>
                      <span class="action-timeline-badge">{{ a.timeline }}</span>
                    </div>
                    <p class="action-plan-text">{{ a.action }}</p>
                    <p v-if="a.rationale" class="action-plan-rationale">{{ a.rationale }}</p>
                  </div>
                </div>
              </div>

              <div v-if="decisionPayload.decision_criteria?.length" class="decision-section criteria-section">
                <h4>Decision Criteria</h4>
                <p class="criteria-desc">Validate these before acting on the verdict</p>
                <div class="criteria-list">
                  <label v-for="(dc, i) in decisionPayload.decision_criteria" :key="i" class="criteria-item">
                    <input type="checkbox" class="criteria-checkbox" />
                    <span class="criteria-text">{{ dc }}</span>
                  </label>
                </div>
              </div>

              <div v-if="decisionPayload.monitoring_indicators?.length" class="decision-section monitoring-section">
                <h4>Monitoring Indicators</h4>
                <div class="monitoring-grid">
                  <div v-for="(m, i) in decisionPayload.monitoring_indicators" :key="i" class="monitoring-card">
                    <div class="monitoring-indicator-name">{{ m.indicator }}</div>
                    <div class="monitoring-row">
                      <span class="monitoring-label">Current</span>
                      <span class="monitoring-value">{{ m.current_state }}</span>
                    </div>
                    <div class="monitoring-row">
                      <span class="monitoring-label">Threshold</span>
                      <span class="monitoring-value monitoring-threshold">{{ m.threshold }}</span>
                    </div>
                    <div class="monitoring-row">
                      <span class="monitoring-label">If triggered</span>
                      <span class="monitoring-value monitoring-action">{{ m.action_if_triggered }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div v-if="decisionPayload.time_sensitivity" class="decision-section time-sensitivity-section">
                <h4>Time Sensitivity</h4>
                <div class="time-sensitivity-card">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                  <span>{{ decisionPayload.time_sensitivity }}</span>
                </div>
              </div>

              <div v-if="scenarioLadder.length" class="decision-section scenario-outcomes-section">
                <h4>Scenario Outcomes</h4>
                <div class="scenario-outcomes">
                  <div v-for="(sc, i) in scenarioLadder" :key="i" class="scenario-outcome-card">
                    <div class="scenario-outcome-header">
                      <span class="scenario-outcome-name">{{ sc.name }}</span>
                      <span v-if="sc.qualitative_only" class="qualitative-tag">
                        <svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                        qualitative estimate
                      </span>
                      <span v-else class="data-backed-tag">
                        <svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                        data-backed
                      </span>
                    </div>
                    <div v-if="sc.assumptions?.length" class="scenario-assumptions">
                      <span class="scenario-assumptions-label">Assumptions</span>
                      <ul class="scenario-assumptions-list">
                        <li v-for="(a, ai) in sc.assumptions" :key="ai">{{ a }}</li>
                      </ul>
                    </div>
                    <div v-if="sc.probability_range && sc.probability_range.low != null" class="probability-bar-container">
                      <div class="probability-bar">
                        <div class="prob-segment prob-low" :style="{ width: (sc.probability_range.low ?? 0) + '%' }"></div>
                        <div class="prob-segment prob-mid" :style="{ width: ((sc.probability_range.mid ?? 0) - (sc.probability_range.low ?? 0)) + '%' }"></div>
                        <div class="prob-segment prob-high" :style="{ width: ((sc.probability_range.high ?? 0) - (sc.probability_range.mid ?? 0)) + '%' }"></div>
                      </div>
                      <div class="probability-labels">
                        <span>{{ sc.probability_range.low ?? 0 }}%</span>
                        <span>{{ sc.probability_range.mid ?? 0 }}%</span>
                        <span>{{ sc.probability_range.high ?? 0 }}%</span>
                      </div>
                    </div>
                    <div v-if="sc._meta?.mc_ci_95" class="scenario-mc-overlay">
                      <span class="scenario-mc-label">MC 95% CI:</span>
                      <span class="scenario-mc-range">[{{ sc._meta.mc_ci_95[0]?.toFixed(1) }}%, {{ sc._meta.mc_ci_95[1]?.toFixed(1) }}%]</span>
                      <span v-if="sc._meta.mc_mean" class="scenario-mc-mean">mean {{ sc._meta.mc_mean?.toFixed(1) }}%</span>
                    </div>
                    <div v-if="sc._meta?.non_exhaustive" class="scenario-non-exhaustive">
                      Scenario probabilities sum to {{ sc._meta.probability_sum }}% (non-exhaustive)
                    </div>
                    <p v-if="sc.outcome_narrative" class="scenario-outcome-narrative">{{ sc.outcome_narrative }}</p>
                  </div>
                </div>
              </div>
            </div>

            <!-- Consistency Warnings -->
            <div v-if="consistencyWarnings.length" class="decision-section consistency-warnings-section">
              <h4>Data Consistency Notes</h4>
              <div v-for="(w, i) in consistencyWarnings" :key="i" class="consistency-warning">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <span>{{ w.message }}</span>
              </div>
            </div>
          </div>

          <!-- Sources and Assumptions (from payload grounding, shown after report completes) -->
          <div v-if="isComplete && groundingData" class="grounding-panel">
            <div class="grounding-header" @click="groundingExpanded = !groundingExpanded">
              <h3 class="grounding-title">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                Sources and Assumptions
              </h3>
              <svg class="grounding-chevron" :class="{ 'is-open': groundingExpanded }" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </div>
            <div v-if="groundingExpanded" class="grounding-body">
              <div v-if="groundingSources.length" class="grounding-subsection">
                <h4>Data Sources</h4>
                <div class="source-list">
                  <span v-for="(src, i) in groundingSources" :key="i" class="source-badge">{{ src }}</span>
                </div>
              </div>

              <div v-if="groundingClaims.length" class="grounding-subsection">
                <h4>Key Assumptions</h4>
                <ul class="claims-list">
                  <li v-for="(claim, i) in groundingClaims" :key="i" class="claim-item">
                    <span class="claim-badge" :class="claim.classification === 'user_provided_context' ? 'badge-user' : 'badge-research'">
                      {{ claim.classification === 'user_provided_context' ? 'User Provided' : 'Research' }}
                    </span>
                    <span class="claim-text">{{ claim.text }}</span>
                  </li>
                </ul>
              </div>

              <div v-if="stalenessWarnings.length" class="grounding-subsection">
                <h4>Freshness Notices</h4>
                <div class="staleness-list">
                  <div v-for="(w, i) in stalenessWarnings" :key="i" class="staleness-badge">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                    {{ typeof w === 'string' ? w : w.message }}
                  </div>
                </div>
              </div>

              <p v-if="!groundingSources.length && !groundingClaims.length" class="grounding-empty">No structured grounding data available for this simulation.</p>
            </div>
          </div>

          <!-- Simulation Analytics Dashboard (from quant payload) -->
          <div v-if="isComplete && hasQuantData" class="quant-dashboard">
            <div class="quant-dashboard-header">
              <h3 class="quant-dashboard-title">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
                Simulation Analytics
              </h3>
            </div>

            <div class="quant-grid">
              <!-- Escalation Timeline -->
              <div v-if="escalationData && escalationData.intensity_curve?.length" class="quant-card quant-card-wide">
                <div class="quant-card-header">
                  <h4>Escalation Timeline</h4>
                  <span class="quant-trend-badge" :class="'trend-' + (escalationData.overall_trend || 'stable')">
                    {{ escalationData.overall_trend }}
                  </span>
                </div>
                <div class="escalation-chart">
                  <div class="escalation-bars">
                    <div 
                      v-for="(point, i) in escalationData.intensity_curve" 
                      :key="i" 
                      class="escalation-bar-wrapper"
                      :title="'Round ' + point.round + ': ' + point.total_actions + ' actions'"
                    >
                      <div 
                        class="escalation-bar" 
                        :class="{ 'is-peak': point.round === escalationData.peak_round }"
                        :style="{ height: (point.normalized_intensity * 100) + '%' }"
                      ></div>
                      <span class="escalation-round-label">{{ point.round }}</span>
                    </div>
                  </div>
                  <div v-if="escalationData.turning_points?.length" class="escalation-turning-points">
                    <span v-for="(tp, i) in escalationData.turning_points" :key="i" class="turning-point-tag">
                      R{{ tp.round }}: {{ tp.description }}
                    </span>
                  </div>
                </div>
                <div class="escalation-meta">
                  <span>{{ escalationData.total_rounds }} rounds</span>
                  <span>Peak: Round {{ escalationData.peak_round }}</span>
                  <span v-if="escalationData.escalation_detected" class="escalation-alert">Escalation detected</span>
                </div>
              </div>

              <!-- Stance Distribution -->
              <div v-if="stanceData && stanceData.position_distribution" class="quant-card">
                <div class="quant-card-header">
                  <h4>Stance Distribution</h4>
                  <span class="quant-agents-count">{{ stanceData.agents_analyzed }} agents</span>
                </div>
                <div class="stance-bars">
                  <div v-for="position in ['supportive', 'opposing', 'neutral', 'ambivalent']" :key="position" class="stance-row">
                    <span class="stance-label">{{ position }}</span>
                    <div class="stance-bar-track">
                      <div class="stance-bar-fill" :class="'stance-' + position" :style="{ width: (stanceData.position_distribution[position] || 0) + '%' }"></div>
                    </div>
                    <span class="stance-pct">{{ (stanceData.position_distribution[position] || 0).toFixed(0) }}%</span>
                  </div>
                </div>
                <div v-if="consensusData" class="consensus-meta">
                  <div class="consensus-stat">
                    <span class="consensus-stat-label">Polarization</span>
                    <span class="consensus-stat-value" :class="consensusData.polarization_index > 0.7 ? 'pol-high' : consensusData.polarization_index > 0.4 ? 'pol-moderate' : 'pol-low'">
                      {{ (consensusData.polarization_index * 100).toFixed(0) }}%
                    </span>
                  </div>
                  <div class="consensus-stat">
                    <span class="consensus-stat-label">Agreement</span>
                    <span class="consensus-stat-value">{{ (consensusData.agreement_ratio || 0).toFixed(0) }}%</span>
                  </div>
                  <div class="consensus-stat">
                    <span class="consensus-stat-label">Factions</span>
                    <span class="consensus-stat-value">{{ consensusData.faction_count }}</span>
                  </div>
                </div>
                <div v-if="consensusData?.key_fault_lines?.length" class="fault-lines">
                  <span v-for="(fl, i) in consensusData.key_fault_lines" :key="i" class="fault-line-tag">{{ fl }}</span>
                </div>
              </div>

              <!-- Risk Heatmap -->
              <div v-if="riskMatrixData && riskMatrixData.risks?.length" class="quant-card">
                <div class="quant-card-header">
                  <h4>Risk Matrix</h4>
                  <span class="quant-risk-count">{{ riskMatrixData.risks.length }} risks</span>
                </div>
                <div class="risk-grid">
                  <div class="risk-grid-labels">
                    <span class="risk-axis-label risk-y-label">Impact</span>
                    <span class="risk-axis-label risk-x-label">Likelihood</span>
                  </div>
                  <div class="risk-grid-cells">
                    <template v-for="impact in [5, 4, 3, 2, 1]" :key="'row-' + impact">
                      <div v-for="likelihood in [1, 2, 3, 4, 5]" :key="'cell-' + impact + '-' + likelihood" 
                        class="risk-cell" 
                        :class="getRiskCellClass(likelihood, impact)"
                      >
                        <span v-for="(r, ri) in getRisksInCell(likelihood, impact)" :key="ri" class="risk-dot" :title="r.risk">
                          {{ ri + 1 }}
                        </span>
                      </div>
                    </template>
                  </div>
                </div>
                <div class="risk-legend">
                  <div v-for="(r, i) in riskMatrixData.top_risks?.slice(0, 3)" :key="i" class="risk-legend-item">
                    <span class="risk-legend-dot" :class="'severity-' + r.severity"></span>
                    <span class="risk-legend-text">{{ r.risk }}</span>
                  </div>
                </div>
                <p v-if="riskMatrixData.risk_summary" class="risk-summary-text">{{ riskMatrixData.risk_summary }}</p>
              </div>

              <!-- Stakeholder Impact Matrix -->
              <div v-if="stakeholderData?.rows?.length" class="quant-card quant-card-wide">
                <div class="quant-card-header">
                  <h4>Stakeholder Impact</h4>
                </div>
                <div class="stakeholder-table-wrapper">
                  <table class="stakeholder-table">
                    <thead>
                      <tr>
                        <th>Type</th>
                        <th>Majority Stance</th>
                        <th>Intensity</th>
                        <th>Activity</th>
                        <th>Escalation</th>
                        <th>Voice Share</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, i) in stakeholderData.rows" :key="i">
                        <td class="stakeholder-type">{{ row.entity_type }}</td>
                        <td><span class="stance-mini-badge" :class="'stance-' + row.stance_majority">{{ row.stance_majority }}</span></td>
                        <td>
                          <div class="intensity-bar-mini">
                            <div class="intensity-fill" :style="{ width: (row.avg_intensity / 5 * 100) + '%' }"></div>
                          </div>
                          <span class="intensity-value">{{ row.avg_intensity.toFixed(1) }}</span>
                        </td>
                        <td :class="row.activity_index > 1.5 ? 'activity-high' : row.activity_index < 0.5 ? 'activity-low' : ''">
                          {{ row.activity_index.toFixed(2) }}x
                        </td>
                        <td :class="row.escalation_exposure > 30 ? 'escalation-high' : ''">
                          {{ row.escalation_exposure.toFixed(1) }}%
                        </td>
                        <td>{{ row.voice_share_pct.toFixed(1) }}%</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- Simulation Activity Summary -->
              <div v-if="simulationMetrics" class="quant-card">
                <div class="quant-card-header">
                  <h4>Activity Summary</h4>
                </div>
                <div class="activity-stats">
                  <div class="activity-stat">
                    <span class="activity-stat-value">{{ simulationMetrics.total_actions?.toLocaleString() }}</span>
                    <span class="activity-stat-label">Total Actions</span>
                  </div>
                  <div class="activity-stat">
                    <span class="activity-stat-value">{{ simulationMetrics.total_agents }}</span>
                    <span class="activity-stat-label">Agents</span>
                  </div>
                  <div class="activity-stat">
                    <span class="activity-stat-value">{{ simulationMetrics.total_rounds }}</span>
                    <span class="activity-stat-label">Rounds</span>
                  </div>
                  <div class="activity-stat">
                    <span class="activity-stat-value">{{ (simulationMetrics.engagement_rate || 0).toFixed(1) }}%</span>
                    <span class="activity-stat-label">Engagement</span>
                  </div>
                </div>
                <div v-if="simulationMetrics.platform_ratio" class="platform-split">
                  <div class="platform-bar">
                    <div class="platform-segment platform-twitter" :style="{ width: (simulationMetrics.platform_ratio.twitter || 0) + '%' }"></div>
                    <div class="platform-segment platform-reddit" :style="{ width: (simulationMetrics.platform_ratio.reddit || 0) + '%' }"></div>
                  </div>
                  <div class="platform-labels">
                    <span class="platform-label"><span class="platform-dot dot-twitter"></span>Twitter {{ (simulationMetrics.platform_ratio.twitter || 0).toFixed(0) }}%</span>
                    <span class="platform-label"><span class="platform-dot dot-reddit"></span>Reddit {{ (simulationMetrics.platform_ratio.reddit || 0).toFixed(0) }}%</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Monte Carlo Analysis (from MC engine) -->
          <div v-if="isComplete && mcComposite" class="mc-dashboard">
            <div class="mc-dashboard-header">
              <h3 class="mc-dashboard-title">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/></svg>
                Probabilistic Analysis
              </h3>
              <div class="mc-convergence-badge" :class="mcComposite.convergence?.converged ? 'converged' : 'not-converged'">
                <span class="mc-conv-dot"></span>
                {{ mcComposite.convergence?.converged ? 'Converged' : 'Low confidence' }}
                <span class="mc-iterations">{{ mcComposite.metadata?.iterations?.toLocaleString() }} iterations</span>
              </div>
            </div>

            <!-- Composite Distribution Chart -->
            <div class="mc-card mc-hero-card">
              <div class="mc-card-header">
                <h4>Overall Scenario Favorability</h4>
                <span class="mc-disclaimer">simulation-derived uncertainty envelope</span>
              </div>

              <div class="mc-histogram">
                <div class="mc-histogram-bars">
                  <div 
                    v-for="(bin, i) in mcComposite.histogram" 
                    :key="i"
                    class="mc-hist-bar-wrapper"
                    :title="bin.center?.toFixed(1) + '%: ' + bin.count + ' samples (' + bin.percentage?.toFixed(1) + '%)'"
                  >
                    <div 
                      class="mc-hist-bar"
                      :class="getMcBarClass(bin, mcComposite.confidence_intervals)"
                      :style="{ height: getHistBarHeight(bin, mcComposite.histogram) + '%' }"
                    ></div>
                  </div>
                </div>
                <div class="mc-histogram-axis">
                  <span>{{ mcComposite.histogram?.[0]?.min?.toFixed(0) }}%</span>
                  <span>{{ mcComposite.mean?.toFixed(1) }}%</span>
                  <span>{{ mcComposite.histogram?.[mcComposite.histogram.length - 1]?.max?.toFixed(0) }}%</span>
                </div>
              </div>

              <div class="mc-ci-bands">
                <div v-for="(ci, level) in mcComposite.confidence_intervals" :key="level" class="mc-ci-row">
                  <span class="mc-ci-label">{{ level }} CI</span>
                  <div class="mc-ci-bar-track">
                    <div 
                      class="mc-ci-bar-fill" 
                      :class="'ci-level-' + level.replace('%', '')"
                      :style="getCiBandStyle(ci, mcComposite)"
                    ></div>
                    <div class="mc-ci-mean-marker" :style="getMeanMarkerStyle(mcComposite)"></div>
                  </div>
                  <span class="mc-ci-range">[{{ ci[0]?.toFixed(1) }}%, {{ ci[1]?.toFixed(1) }}%]</span>
                </div>
              </div>

              <div class="mc-summary-stats">
                <div class="mc-stat">
                  <span class="mc-stat-label">Mean</span>
                  <span class="mc-stat-value">{{ mcComposite.mean?.toFixed(1) }}%</span>
                </div>
                <div class="mc-stat">
                  <span class="mc-stat-label">Median</span>
                  <span class="mc-stat-value">{{ mcComposite.median?.toFixed(1) }}%</span>
                </div>
                <div class="mc-stat">
                  <span class="mc-stat-label">Std Dev</span>
                  <span class="mc-stat-value">{{ mcComposite.std_dev?.toFixed(2) }}%</span>
                </div>
                <div class="mc-stat">
                  <span class="mc-stat-label">Mode</span>
                  <span class="mc-stat-value">{{ mcComposite.mode?.toFixed(1) }}%</span>
                </div>
              </div>
            </div>

            <!-- Tail Risk Callout -->
            <div v-if="mcComposite.tail_risk" class="mc-card mc-tail-risk-card">
              <div class="mc-tail-icon">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
              </div>
              <div class="mc-tail-content">
                <h4>Tail Risk Assessment</h4>
                <p>In the <strong>worst 5%</strong> of simulated outcomes, the expected scenario favorability is <strong>{{ mcComposite.tail_risk.expected_shortfall?.toFixed(1) }}%</strong>.</p>
                <div class="mc-tail-stats">
                  <span>1st percentile: {{ mcComposite.tail_risk.percentile_1?.toFixed(1) }}%</span>
                  <span>5th percentile: {{ mcComposite.tail_risk.percentile_5?.toFixed(1) }}%</span>
                  <span>99th percentile: {{ mcComposite.tail_risk.percentile_99?.toFixed(1) }}%</span>
                </div>
              </div>
            </div>

            <!-- Per-Outcome MC Results -->
            <div v-if="mcPerOutcome.length" class="mc-per-outcome">
              <h4 class="mc-per-outcome-title">Per-Outcome Confidence Intervals</h4>
              <div class="mc-outcome-grid">
                <div v-for="(item, i) in mcPerOutcome" :key="i" class="mc-outcome-card">
                  <div class="mc-outcome-name">{{ item.outcome }}</div>
                  <div class="mc-outcome-stats">
                    <span class="mc-outcome-mean">{{ item.monte_carlo?.mean?.toFixed(1) }}%</span>
                    <span class="mc-outcome-ci">
                      95% CI: [{{ item.monte_carlo?.confidence_intervals?.['95%']?.[0]?.toFixed(1) }}%, {{ item.monte_carlo?.confidence_intervals?.['95%']?.[1]?.toFixed(1) }}%]
                    </span>
                  </div>
                  <div class="mc-outcome-bar-track">
                    <div 
                      class="mc-outcome-bar-fill"
                      :style="{ 
                        left: (item.monte_carlo?.confidence_intervals?.['95%']?.[0] || 0) + '%',
                        width: ((item.monte_carlo?.confidence_intervals?.['95%']?.[1] || 0) - (item.monte_carlo?.confidence_intervals?.['95%']?.[0] || 0)) + '%'
                      }"
                    ></div>
                    <div class="mc-outcome-mean-dot" :style="{ left: (item.monte_carlo?.mean || 0) + '%' }"></div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Historical Comparison (from deep research precedents) -->
          <div v-if="isComplete && historicalPrecedents.length" class="historical-dashboard">
            <div class="historical-dashboard-header">
              <h3 class="historical-dashboard-title">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                Historical Precedents
              </h3>
              <span class="historical-count">{{ historicalPrecedents.length }} cases</span>
            </div>
            <div class="precedent-cards">
              <div v-for="(p, i) in historicalPrecedents" :key="i" class="precedent-card">
                <div class="precedent-card-header">
                  <span class="precedent-event">{{ p.event }}</span>
                  <div class="precedent-relevance">
                    <div class="relevance-bar">
                      <div class="relevance-fill" :style="{ width: ((p.relevance_score || 0) * 100) + '%' }"></div>
                    </div>
                    <span class="relevance-label">{{ ((p.relevance_score || 0) * 100).toFixed(0) }}% relevant</span>
                  </div>
                </div>
                <p v-if="p.outcome" class="precedent-outcome">{{ p.outcome }}</p>
                <div class="precedent-meta">
                  <span v-if="p.timeline" class="precedent-meta-item">
                    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                    {{ p.timeline }}
                  </span>
                  <span v-if="p.key_metric" class="precedent-metric">{{ p.key_metric }}</span>
                </div>
                <a v-if="p.source_url" :href="p.source_url" target="_blank" rel="noopener" class="precedent-source-link">Source</a>
              </div>
            </div>
          </div>

          <!-- Sections List -->
          <div class="sections-list">
            <div 
              v-for="(section, idx) in reportOutline.sections" 
              :key="idx"
              class="report-section-item"
              :class="{ 
                'is-active': currentSectionIndex === idx + 1,
                'is-completed': isSectionCompleted(idx + 1),
                'is-pending': !isSectionCompleted(idx + 1) && currentSectionIndex !== idx + 1
              }"
            >
              <div class="section-header-row" @click="toggleSectionCollapse(idx)" :class="{ 'clickable': isSectionCompleted(idx + 1) }">
                <span class="section-number">{{ String(idx + 1).padStart(2, '0') }}</span>
                <h3 class="section-title">{{ section.title }}</h3>
                <svg 
                  v-if="isSectionCompleted(idx + 1)" 
                  class="collapse-icon" 
                  :class="{ 'is-collapsed': collapsedSections.has(idx) }"
                  viewBox="0 0 24 24" 
                  width="20" 
                  height="20" 
                  fill="none" 
                  stroke="currentColor" 
                  stroke-width="2"
                >
                  <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
              </div>
              
              <div class="section-body" v-show="!collapsedSections.has(idx)">
                <!-- Completed Content -->
                <div v-if="generatedSections[idx + 1]" class="generated-content" v-html="renderMarkdown(generatedSections[idx + 1])"></div>
                
                <!-- Loading State -->
                <div v-else-if="currentSectionIndex === idx + 1" class="loading-state">
                  <div class="loading-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <circle cx="12" cy="12" r="10" stroke-width="4" stroke="#E5E7EB"></circle>
                      <path d="M12 2a10 10 0 0 1 10 10" stroke-width="4" stroke="#4B5563" stroke-linecap="round"></path>
                    </svg>
                  </div>
                  <span class="loading-text">Generating {{ section.title }}...</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Follow-Up Suggestions (shown after report completes) -->
        <div v-if="isComplete && followUpSuggestions.length > 0" class="followup-section">
          <div class="followup-header">
            <h3 class="followup-title">What Else Should You Test?</h3>
            <p class="followup-desc">Explore related scenarios to strengthen your analysis</p>
          </div>
          <div class="followup-cards">
            <div
              v-for="(s, i) in followUpSuggestions"
              :key="i"
              class="followup-card"
              @click="runFollowUp(s)"
            >
              <div class="followup-card-body">
                <div class="followup-card-top">
                  <span v-if="s.variation_type" class="variation-badge" :class="'vtype-' + s.variation_type">
                    {{ s.variation_type }} {{ s.magnitude || '' }}
                  </span>
                </div>
                <h4 class="followup-card-title">{{ s.title }}</h4>
                <p class="followup-card-change">{{ s.change_summary }}</p>
              </div>
              <span class="followup-run-btn">Run This &rarr;</span>
            </div>
          </div>
        </div>
        <div v-if="isComplete && followUpsLoading" class="followup-loading">
          <div class="followup-spinner"></div>
          <span>Generating follow-up suggestions...</span>
        </div>

        <!-- Recurring Prompts (shown after report completes) -->
        <div v-if="isComplete" class="recurring-section">
          <div class="recurring-header">
            <h3 class="recurring-title">Track This Decision</h3>
          </div>
          <div class="recurring-actions">
            <button class="recurring-btn" @click="setReminder('week')">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              Re-run next week with updated data
            </button>
            <button class="recurring-btn" @click="setReminder('month')">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
              Monitor this scenario monthly
            </button>
          </div>
          <p v-if="reminderSet" class="reminder-confirm">Reminder set. We'll notify you when it's time to re-run.</p>
        </div>

        <!-- Waiting State -->
        <div v-if="!reportOutline" class="waiting-placeholder">
          <div class="waiting-animation">
            <div class="waiting-ring"></div>
            <div class="waiting-ring"></div>
            <div class="waiting-ring"></div>
          </div>
          <span class="waiting-text">Waiting for Report Agent...</span>
        </div>
      </div>

      <!-- RIGHT PANEL: Workflow Timeline -->
      <div class="right-panel" ref="rightPanel">
        <div class="panel-header" :class="`panel-header--${activeStep.status}`" v-if="!isComplete">
          <span class="header-dot" v-if="activeStep.status === 'active'"></span>
          <span class="header-index mono">{{ activeStep.noLabel }}</span>
          <span class="header-title">{{ activeStep.title }}</span>
          <span class="header-meta mono" v-if="activeStep.meta">{{ activeStep.meta }}</span>
        </div>

        <!-- Workflow Overview (flat, status-based palette) -->
        <div class="workflow-overview" v-if="agentLogs.length > 0 || reportOutline">
          <div class="workflow-metrics">
            <div class="metric">
              <span class="metric-label">Sections</span>
              <span class="metric-value mono">{{ completedSections }}/{{ totalSections }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">Elapsed</span>
              <span class="metric-value mono">{{ formatElapsedTime }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">Tools</span>
              <span class="metric-value mono">{{ totalToolCalls }}</span>
            </div>
            <div class="metric metric-right">
              <span class="metric-pill" :class="`pill--${statusClass}`">{{ statusText }}</span>
            </div>
          </div>

          <div class="workflow-steps" v-if="workflowSteps.length > 0">
            <div
              v-for="(step, sidx) in workflowSteps"
              :key="step.key"
              class="wf-step"
              :class="`wf-step--${step.status}`"
            >
              <div class="wf-step-connector">
                <div class="wf-step-dot"></div>
                <div class="wf-step-line" v-if="sidx < workflowSteps.length - 1"></div>
              </div>

              <div class="wf-step-content">
                <div class="wf-step-title-row">
                  <span class="wf-step-index mono">{{ step.noLabel }}</span>
                  <span class="wf-step-title">{{ step.title }}</span>
                  <span class="wf-step-meta mono" v-if="step.meta">{{ step.meta }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Next Step Button - shown when complete -->
          <button v-if="isComplete" class="next-step-btn" @click="goToInteraction">
            <span>Proceed to Deep Interaction</span>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="5" y1="12" x2="19" y2="12"></line>
              <polyline points="12 5 19 12 12 19"></polyline>
            </svg>
          </button>

          <div class="workflow-divider"></div>
        </div>

        <div class="workflow-timeline">
          <TransitionGroup name="timeline-item">
            <div 
              v-for="(log, idx) in displayLogs" 
              :key="log.timestamp + '-' + idx"
              class="timeline-item"
              :class="getTimelineItemClass(log, idx, displayLogs.length)"
            >
              <!-- Timeline Connector -->
              <div class="timeline-connector">
                <div class="connector-dot" :class="getConnectorClass(log, idx, displayLogs.length)"></div>
                <div class="connector-line" v-if="idx < displayLogs.length - 1"></div>
              </div>
              
              <!-- Timeline Content -->
              <div class="timeline-content">
                <div class="timeline-header">
                  <span class="action-label">{{ getActionLabel(log.action) }}</span>
                  <span class="action-time">{{ formatTime(log.timestamp) }}</span>
                </div>
                
                <!-- Action Body - Different for each type -->
                <div class="timeline-body" :class="{ 'collapsed': isLogCollapsed(log) }" @click="toggleLogExpand(log)">
                  
                  <!-- Report Start -->
                  <template v-if="log.action === 'report_start'">
                    <div class="info-row">
                      <span class="info-key">Simulation</span>
                      <span class="info-val mono">{{ log.details?.simulation_id }}</span>
                    </div>
                    <div class="info-row" v-if="log.details?.simulation_requirement">
                      <span class="info-key">Requirement</span>
                      <span class="info-val">{{ log.details.simulation_requirement }}</span>
                    </div>
                  </template>

                  <!-- Planning -->
                  <template v-if="log.action === 'planning_start'">
                    <div class="status-message planning">{{ log.details?.message }}</div>
                  </template>
                  <template v-if="log.action === 'planning_complete'">
                    <div class="status-message success">{{ log.details?.message }}</div>
                    <div class="outline-badge" v-if="log.details?.outline">
                      {{ log.details.outline.sections?.length || 0 }} sections planned
                    </div>
                  </template>

                  <!-- Section Start -->
                  <template v-if="log.action === 'section_start'">
                    <div class="section-tag">
                      <span class="tag-num">#{{ log.section_index }}</span>
                      <span class="tag-title">{{ log.section_title }}</span>
                    </div>
                  </template>
                  
                  <!-- Section Content Generated (content ready, section may not be fully complete) -->
                  <template v-if="log.action === 'section_content'">
                    <div class="section-tag content-ready">
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 20h9"></path>
                        <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
                      </svg>
                      <span class="tag-title">{{ log.section_title }}</span>
                    </div>
                  </template>

                  <!-- Section Complete (section generation complete) -->
                  <template v-if="log.action === 'section_complete'">
                    <div class="section-tag completed">
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="20 6 9 17 4 12"></polyline>
                      </svg>
                      <span class="tag-title">{{ log.section_title }}</span>
                    </div>
                  </template>

                  <!-- Tool Call -->
                  <template v-if="log.action === 'tool_call'">
                    <div class="tool-badge" :class="'tool-' + getToolColor(log.details?.tool_name)">
                      <!-- Deep Insight - Lightbulb -->
                      <svg v-if="getToolIcon(log.details?.tool_name) === 'lightbulb'" class="tool-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.5V17a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2.5A7 7 0 0 0 12 2z"></path>
                      </svg>
                      <!-- Panorama Search - Globe -->
                      <svg v-else-if="getToolIcon(log.details?.tool_name) === 'globe'" class="tool-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
                      </svg>
                      <!-- Agent Interview - Users -->
                      <svg v-else-if="getToolIcon(log.details?.tool_name) === 'users'" class="tool-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                        <circle cx="9" cy="7" r="4"></circle>
                        <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"></path>
                      </svg>
                      <!-- Quick Search - Zap -->
                      <svg v-else-if="getToolIcon(log.details?.tool_name) === 'zap'" class="tool-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
                      </svg>
                      <!-- Graph Stats - Chart -->
                      <svg v-else-if="getToolIcon(log.details?.tool_name) === 'chart'" class="tool-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="20" x2="18" y2="10"></line>
                        <line x1="12" y1="20" x2="12" y2="4"></line>
                        <line x1="6" y1="20" x2="6" y2="14"></line>
                      </svg>
                      <!-- Entity Query - Database -->
                      <svg v-else-if="getToolIcon(log.details?.tool_name) === 'database'" class="tool-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
                        <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
                        <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
                      </svg>
                      <!-- Default - Tool -->
                      <svg v-else class="tool-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
                      </svg>
                      {{ getToolDisplayName(log.details?.tool_name) }}
                    </div>
                    <div v-if="log.details?.parameters && expandedLogs.has(log.timestamp)" class="tool-params">
                      <pre>{{ formatParams(log.details.parameters) }}</pre>
                    </div>
                  </template>

                  <!-- Tool Result -->
                  <template v-if="log.action === 'tool_result'">
                    <div class="result-wrapper" :class="'result-' + log.details?.tool_name">
                      <!-- Hide result-meta for tools that show stats in their own header -->
                      <div v-if="!['interview_agents', 'insight_forge', 'panorama_search', 'quick_search'].includes(log.details?.tool_name)" class="result-meta">
                        <span class="result-tool">{{ getToolDisplayName(log.details?.tool_name) }}</span>
                        <span class="result-size">{{ formatResultSize(log.details?.result_length) }}</span>
                      </div>
                      
                      <!-- Structured Result Display -->
                      <div v-if="!showRawResult[log.timestamp]" class="result-structured">
                        <!-- Interview Agents - Special Display -->
                        <template v-if="log.details?.tool_name === 'interview_agents'">
                          <InterviewDisplay :result="parseInterview(log.details.result)" :result-length="log.details?.result_length" />
                        </template>
                        
                        <!-- Insight Forge -->
                        <template v-else-if="log.details?.tool_name === 'insight_forge'">
                          <InsightDisplay :result="parseInsightForge(log.details.result)" :result-length="log.details?.result_length" />
                        </template>
                        
                        <!-- Panorama Search -->
                        <template v-else-if="log.details?.tool_name === 'panorama_search'">
                          <PanoramaDisplay :result="parsePanorama(log.details.result)" :result-length="log.details?.result_length" />
                        </template>
                        
                        <!-- Quick Search -->
                        <template v-else-if="log.details?.tool_name === 'quick_search'">
                          <QuickSearchDisplay :result="parseQuickSearch(log.details.result)" :result-length="log.details?.result_length" />
                        </template>
                        
                        <!-- Default -->
                        <template v-else>
                          <pre class="raw-preview">{{ truncateText(log.details?.result, 300) }}</pre>
                        </template>
                      </div>
                      
                      <!-- Raw Result -->
                      <div v-else class="result-raw">
                        <pre>{{ log.details?.result }}</pre>
                      </div>
                    </div>
                  </template>

                  <!-- LLM Response -->
                  <template v-if="log.action === 'llm_response'">
                    <div class="llm-meta">
                      <span class="meta-tag">Iteration {{ log.details?.iteration }}</span>
                      <span class="meta-tag" :class="{ active: log.details?.has_tool_calls }">
                        Tools: {{ log.details?.has_tool_calls ? 'Yes' : 'No' }}
                      </span>
                      <span class="meta-tag" :class="{ active: log.details?.has_final_answer, 'final-answer': log.details?.has_final_answer }">
                        Final: {{ log.details?.has_final_answer ? 'Yes' : 'No' }}
                      </span>
                    </div>
                    <!-- When final answer, show special hint -->
                    <div v-if="log.details?.has_final_answer" class="final-answer-hint">
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="20 6 9 17 4 12"></polyline>
                      </svg>
                      <span>Section "{{ log.section_title }}" content generated</span>
                    </div>
                    <div v-if="expandedLogs.has(log.timestamp) && log.details?.response" class="llm-content">
                      <pre>{{ log.details.response }}</pre>
                    </div>
                  </template>

                  <!-- Report Complete -->
                  <template v-if="log.action === 'report_complete'">
                    <div class="complete-banner">
                      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                        <polyline points="22 4 12 14.01 9 11.01"></polyline>
                      </svg>
                      <span>Report Generation Complete</span>
                    </div>
                  </template>
                </div>

                <!-- Footer: Elapsed Time + Action Buttons -->
                <div class="timeline-footer" v-if="log.elapsed_seconds || (log.action === 'tool_call' && log.details?.parameters) || log.action === 'tool_result' || (log.action === 'llm_response' && log.details?.response)">
                  <span v-if="log.elapsed_seconds" class="elapsed-badge">+{{ log.elapsed_seconds.toFixed(1) }}s</span>
                  <span v-else class="elapsed-placeholder"></span>
                  
                  <div class="footer-actions">
                    <!-- Tool Call: Show/Hide Params -->
                    <button v-if="log.action === 'tool_call' && log.details?.parameters" class="action-btn" @click.stop="toggleLogExpand(log)">
                      {{ expandedLogs.has(log.timestamp) ? 'Hide Params' : 'Show Params' }}
                    </button>
                    
                    <!-- Tool Result: Raw/Structured View -->
                    <button v-if="log.action === 'tool_result'" class="action-btn" @click.stop="toggleRawResult(log.timestamp, $event)">
                      {{ showRawResult[log.timestamp] ? 'Structured View' : 'Raw Output' }}
                    </button>
                    
                    <!-- LLM Response: Show/Hide Response -->
                    <button v-if="log.action === 'llm_response' && log.details?.response" class="action-btn" @click.stop="toggleLogExpand(log)">
                      {{ expandedLogs.has(log.timestamp) ? 'Hide Response' : 'Show Response' }}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </TransitionGroup>

          <!-- Empty State -->
          <div v-if="agentLogs.length === 0 && !isComplete" class="workflow-empty">
            <div class="empty-pulse"></div>
            <span>Waiting for agent activity...</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Bottom Console Logs -->
    <div class="console-logs">
      <div class="log-header">
        <span class="log-title">CONSOLE OUTPUT</span>
        <span class="log-id">{{ reportId || 'NO_REPORT' }}</span>
      </div>
      <div class="log-content" ref="logContent">
        <div class="log-line" v-for="(log, idx) in consoleLogs" :key="idx">
          <span class="log-msg" :class="getLogLevelClass(log)">{{ log }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted, nextTick, reactive } from 'vue'
import { useRouter } from 'vue-router'

import {
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
} from './step4/step4ReportToolDisplays.js'

import { getAgentLog, getConsoleLog, getReportPayload } from '../api/report'
import { suggestFollowups, createReminder } from '../api/simulation'
import { setPendingUpload } from '../store/pendingUpload'
import { trackEvent } from '../lib/analytics'

const router = useRouter()

const props = defineProps({
  reportId: String,
  simulationId: String,
  systemLogs: Array
})

const emit = defineEmits(['add-log', 'update-status'])

// Navigation
const goToInteraction = () => {
  if (props.reportId) {
    router.push({ name: 'Interaction', params: { reportId: props.reportId } })
  }
}

const runFollowUp = (suggestion) => {
  trackEvent('followup_clicked', { title: suggestion.title })
  setPendingUpload([], suggestion.scenario, null, null)
  router.push({ name: 'Home', query: { prefill: '1' } })
}

const fetchFollowUps = async () => {
  if (!props.simulationId && !props.reportId) return
  followUpsLoading.value = true
  try {
    const res = await suggestFollowups({
      simulation_id: props.simulationId,
      report_id: props.reportId,
    })
    if (res.data?.suggestions) {
      followUpSuggestions.value = res.data.suggestions
    }
  } catch (e) {
    console.error('Failed to fetch follow-up suggestions:', e)
  } finally {
    followUpsLoading.value = false
  }
}

const setReminder = async (period) => {
  const now = new Date()
  const remindAt = period === 'week'
    ? new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000)
    : new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000)
  try {
    await createReminder({
      simulation_id: props.simulationId || '',
      scenario: reportOutline.value?.title || '',
      remind_at: remindAt.toISOString(),
    })
    reminderSet.value = true
  } catch (e) {
    console.error('Failed to set reminder:', e)
  }
}

// State
const agentLogs = ref([])
const consoleLogs = ref([])
const agentLogLine = ref(0)
const consoleLogLine = ref(0)
const reportOutline = ref(null)
const reportPayload = ref(null)
const currentSectionIndex = ref(null)
const generatedSections = ref({})
const expandedContent = ref(new Set())
const expandedLogs = ref(new Set())
const collapsedSections = ref(new Set())
const isComplete = ref(false)
const startTime = ref(null)
const leftPanel = ref(null)
const rightPanel = ref(null)
const logContent = ref(null)
const showRawResult = reactive({})

const followUpSuggestions = ref([])
const followUpsLoading = ref(false)
const reminderSet = ref(false)
const groundingExpanded = ref(false)

// Toggle functions
const toggleRawResult = (timestamp, event) => {
  // Save button position relative to viewport
  const button = event?.target
  const buttonRect = button?.getBoundingClientRect()
  const buttonTopBeforeToggle = buttonRect?.top
  
  // Toggle state
  showRawResult[timestamp] = !showRawResult[timestamp]
  
  // After DOM update, adjust scroll to keep button in same position
  if (button && buttonTopBeforeToggle !== undefined && rightPanel.value) {
    nextTick(() => {
      const newButtonRect = button.getBoundingClientRect()
      const buttonTopAfterToggle = newButtonRect.top
      const scrollDelta = buttonTopAfterToggle - buttonTopBeforeToggle
      
      // Adjust scroll position
      rightPanel.value.scrollTop += scrollDelta
    })
  }
}

const toggleSectionContent = (idx) => {
  if (!generatedSections.value[idx + 1]) return
  const newSet = new Set(expandedContent.value)
  if (newSet.has(idx)) {
    newSet.delete(idx)
  } else {
    newSet.add(idx)
  }
  expandedContent.value = newSet
}

const toggleSectionCollapse = (idx) => {
  // Only completed sections can be collapsed
  if (!generatedSections.value[idx + 1]) return
  const newSet = new Set(collapsedSections.value)
  if (newSet.has(idx)) {
    newSet.delete(idx)
  } else {
    newSet.add(idx)
  }
  collapsedSections.value = newSet
}

const toggleLogExpand = (log) => {
  const newSet = new Set(expandedLogs.value)
  if (newSet.has(log.timestamp)) {
    newSet.delete(log.timestamp)
  } else {
    newSet.add(log.timestamp)
  }
  expandedLogs.value = newSet
}

const isLogCollapsed = (log) => {
  if (['tool_call', 'tool_result', 'llm_response'].includes(log.action)) {
    return !expandedLogs.value.has(log.timestamp)
  }
  return false
}


// Computed
const statusClass = computed(() => {
  if (isComplete.value) return 'completed'
  if (agentLogs.value.length > 0) return 'processing'
  return 'pending'
})

const statusText = computed(() => {
  if (isComplete.value) return 'Completed'
  if (agentLogs.value.length > 0) return 'Generating...'
  return 'Waiting'
})

const totalSections = computed(() => {
  return reportOutline.value?.sections?.length || 0
})

const completedSections = computed(() => {
  return Object.keys(generatedSections.value).length
})

const progressPercent = computed(() => {
  if (totalSections.value === 0) return 0
  return Math.round((completedSections.value / totalSections.value) * 100)
})

const totalToolCalls = computed(() => {
  return agentLogs.value.filter(l => l.action === 'tool_call').length
})

const formatElapsedTime = computed(() => {
  if (!startTime.value) return '0s'
  const lastLog = agentLogs.value[agentLogs.value.length - 1]
  const elapsed = lastLog?.elapsed_seconds || 0
  if (elapsed < 60) return `${Math.round(elapsed)}s`
  const mins = Math.floor(elapsed / 60)
  const secs = Math.round(elapsed % 60)
  return `${mins}m ${secs}s`
})

const displayLogs = computed(() => {
  return agentLogs.value
})

// Workflow steps overview (status-based, no nested cards)
const activeSectionIndex = computed(() => {
  if (isComplete.value) return null
  if (currentSectionIndex.value) return currentSectionIndex.value
  if (totalSections.value > 0 && completedSections.value < totalSections.value) return completedSections.value + 1
  return null
})

const isPlanningDone = computed(() => {
  return !!reportOutline.value?.sections?.length || agentLogs.value.some(l => l.action === 'planning_complete')
})

const isPlanningStarted = computed(() => {
  return agentLogs.value.some(l => l.action === 'planning_start' || l.action === 'report_start')
})

const isFinalizing = computed(() => {
  return !isComplete.value && isPlanningDone.value && totalSections.value > 0 && completedSections.value >= totalSections.value
})

// Current active step (for top display)
const activeStep = computed(() => {
  const steps = workflowSteps.value
  // Find current active step
  const active = steps.find(s => s.status === 'active')
  if (active) return active
  
  // If no active, return last done step
  const doneSteps = steps.filter(s => s.status === 'done')
  if (doneSteps.length > 0) return doneSteps[doneSteps.length - 1]
  
  // Otherwise return first step
  return steps[0] || { noLabel: '--', title: 'Waiting to start', status: 'todo', meta: '' }
})

const workflowSteps = computed(() => {
  const steps = []

  // Planning / Outline
  const planningStatus = isPlanningDone.value ? 'done' : (isPlanningStarted.value ? 'active' : 'todo')
  steps.push({
    key: 'planning',
    noLabel: 'PL',
    title: 'Planning / Outline',
    status: planningStatus,
    meta: planningStatus === 'active' ? 'IN PROGRESS' : ''
  })

  // Sections (if outline exists)
  const sections = reportOutline.value?.sections || []
  sections.forEach((section, i) => {
    const idx = i + 1
    const status = (isComplete.value || !!generatedSections.value[idx])
      ? 'done'
      : (activeSectionIndex.value === idx ? 'active' : 'todo')

    steps.push({
      key: `section-${idx}`,
      noLabel: String(idx).padStart(2, '0'),
      title: section.title,
      status,
      meta: status === 'active' ? 'IN PROGRESS' : ''
    })
  })

  // Complete
  const completeStatus = isComplete.value ? 'done' : (isFinalizing.value ? 'active' : 'todo')
  steps.push({
    key: 'complete',
    noLabel: 'OK',
    title: 'Complete',
    status: completeStatus,
    meta: completeStatus === 'active' ? 'FINALIZING' : ''
  })

  return steps
})

// Methods
const addLog = (msg) => {
  emit('add-log', msg)
}

const isSectionCompleted = (sectionIndex) => {
  return !!generatedSections.value[sectionIndex]
}

const formatTime = (timestamp) => {
  if (!timestamp) return ''
  try {
    return new Date(timestamp).toLocaleTimeString('en-US', { 
      hour12: false, 
      hour: '2-digit', 
      minute: '2-digit', 
      second: '2-digit' 
    })
  } catch {
    return ''
  }
}

const formatParams = (params) => {
  if (!params) return ''
  try {
    return JSON.stringify(params, null, 2)
  } catch {
    return String(params)
  }
}

const formatResultSize = (length) => {
  if (!length) return ''
  if (length < 1000) return `${length} chars`
  return `${(length / 1000).toFixed(1)}k chars`
}

const truncateText = (text, maxLen) => {
  if (!text) return ''
  if (text.length <= maxLen) return text
  return text.substring(0, maxLen) + '...'
}



const getTimelineItemClass = (log, idx, total) => {
  const isLatest = idx === total - 1 && !isComplete.value
  const isMilestone = log.action === 'section_complete' || log.action === 'report_complete'
  return {
    'node--active': isLatest,
    'node--done': !isLatest && isMilestone,
    'node--muted': !isLatest && !isMilestone,
    'node--tool': log.action === 'tool_call' || log.action === 'tool_result'
  }
}

const getConnectorClass = (log, idx, total) => {
  const isLatest = idx === total - 1 && !isComplete.value
  if (isLatest) return 'dot-active'
  if (log.action === 'section_complete' || log.action === 'report_complete') return 'dot-done'
  return 'dot-muted'
}

const getActionLabel = (action) => {
  const labels = {
    'report_start': 'Report Started',
    'planning_start': 'Planning',
    'planning_complete': 'Plan Complete',
    'section_start': 'Section Start',
    'section_content': 'Content Ready',
    'section_complete': 'Section Done',
    'tool_call': 'Tool Call',
    'tool_result': 'Tool Result',
    'llm_response': 'LLM Response',
    'report_complete': 'Complete'
  }
  return labels[action] || action
}

const getLogLevelClass = (log) => {
  if (log.includes('ERROR') || log.includes('Error')) return 'error'
  if (log.includes('WARNING') || log.includes('Warning')) return 'warning'
  // INFO uses default color, not marked as success
  return ''
}

// Polling
let agentLogTimer = null
let consoleLogTimer = null

const fetchAgentLog = async () => {
  if (!props.reportId) return
  
  try {
    const res = await getAgentLog(props.reportId, agentLogLine.value)
    
    if (res.success && res.data) {
      const newLogs = res.data.logs || []
      
      if (newLogs.length > 0) {
        newLogs.forEach(log => {
          agentLogs.value.push(log)
          
          if (log.action === 'planning_complete' && log.details?.outline) {
            reportOutline.value = log.details.outline
          }
          
          if (log.action === 'section_start') {
            currentSectionIndex.value = log.section_index
          }

          // section_complete - section generation complete
          if (log.action === 'section_complete') {
            if (log.details?.content) {
              generatedSections.value[log.section_index] = log.details.content
              // Auto-expand newly generated section
              expandedContent.value.add(log.section_index - 1)
              currentSectionIndex.value = null
            }
          }
          
          if (log.action === 'report_complete') {
            isComplete.value = true
            trackEvent('simulation_completed', { simulation_id: props.simulationId })
            currentSectionIndex.value = null
            emit('update-status', 'completed')
            stopPolling()
            fetchReportPayload()
            fetchFollowUps()
            // Scroll logic handled in nextTick after loop
          }
          
          if (log.action === 'report_start') {
            startTime.value = new Date(log.timestamp)
          }
        })
        
        agentLogLine.value = res.data.from_line + newLogs.length
        
        nextTick(() => {
          if (rightPanel.value) {
            // If task complete, scroll to top; else scroll to bottom for latest logs
            if (isComplete.value) {
              rightPanel.value.scrollTop = 0
            } else {
              rightPanel.value.scrollTop = rightPanel.value.scrollHeight
            }
          }
        })
      }
    }
  } catch (err) {
    console.warn('Failed to fetch agent log:', err)
  }
}

// Extract final answer content from LLM response
const extractFinalContent = (response) => {
  if (!response) return null
  
  // Try extract content inside <final_answer> tag
  const finalAnswerTagMatch = response.match(/<final_answer>([\s\S]*?)<\/final_answer>/)
  if (finalAnswerTagMatch) {
    return finalAnswerTagMatch[1].trim()
  }
  
  // Try find content after Final Answer: (support multiple formats)
  // Format 1: Final Answer:\n\ncontent
  // Format 2: Final Answer: content
  const finalAnswerMatch = response.match(/Final\s*Answer:\s*\n*([\s\S]*)$/i)
  if (finalAnswerMatch) {
    return finalAnswerMatch[1].trim()
  }
  
  // If starts with ## or # or >, may be direct markdown
  const trimmedResponse = response.trim()
  if (trimmedResponse.match(/^[#>]/)) {
    return trimmedResponse
  }
  
  // If content long and has markdown, try remove thought process and return
  if (response.length > 300 && (response.includes('**') || response.includes('>'))) {
    // Remove thought process starting with Thought:
    const thoughtMatch = response.match(/^Thought:[\s\S]*?(?=\n\n[^T]|\n\n$)/i)
    if (thoughtMatch) {
      const afterThought = response.substring(thoughtMatch[0].length).trim()
      if (afterThought.length > 100) {
        return afterThought
      }
    }
  }
  
  return null
}

const fetchConsoleLog = async () => {
  if (!props.reportId) return
  
  try {
    const res = await getConsoleLog(props.reportId, consoleLogLine.value)
    
    if (res.success && res.data) {
      const newLogs = res.data.logs || []
      
      if (newLogs.length > 0) {
        consoleLogs.value.push(...newLogs)
        consoleLogLine.value = res.data.from_line + newLogs.length
        
        nextTick(() => {
          if (logContent.value) {
            logContent.value.scrollTop = logContent.value.scrollHeight
          }
        })
      }
    }
  } catch (err) {
    console.warn('Failed to fetch console log:', err)
  }
}

const fetchReportPayload = async () => {
  if (!props.reportId) return
  try {
    const res = await getReportPayload(props.reportId)
    if (res.success && res.data) {
      reportPayload.value = res.data
    }
  } catch (err) {
    console.warn('Failed to fetch report payload:', err)
  }
}

const decisionPayload = computed(() => reportPayload.value?.decision || null)

const scenarioLadder = computed(() => reportPayload.value?.scenarios || [])

const groundingData = computed(() => reportPayload.value?.grounding || null)
const groundingSources = computed(() => {
  const claims = groundingData.value?.claims || []
  const names = new Set(claims.map(c => c.source || c.source_id || 'Unknown').filter(Boolean))
  return [...names]
})
const groundingClaims = computed(() => groundingData.value?.claims || [])
const stalenessWarnings = computed(() => groundingData.value?.staleness_warnings || [])

const quantData = computed(() => reportPayload.value?.quant || null)
const monteCarloData = computed(() => reportPayload.value?.monte_carlo || null)
const mcComposite = computed(() => monteCarloData.value?.composite || null)
const mcPerOutcome = computed(() => {
  const raw = monteCarloData.value?.per_outcome || []
  return raw.filter(item => item !== null)
})
const escalationData = computed(() => quantData.value?.metrics?.escalation_analysis || null)
const stanceData = computed(() => quantData.value?.positions?.stance_analysis || null)
const consensusData = computed(() => quantData.value?.positions?.consensus_metrics || null)
const riskMatrixData = computed(() => quantData.value?.risks?.risk_matrix || null)
const probabilityData = computed(() => quantData.value?.risks?.probability_assessment || null)
const stakeholderData = computed(() => quantData.value?.stakeholder_matrix || null)
const simulationMetrics = computed(() => quantData.value?.metrics?.simulation_metrics || null)

const consistencyWarnings = computed(() => reportPayload.value?.consistency_warnings || [])
const historicalComparison = computed(() => reportPayload.value?.historical_comparison || null)
const historicalPrecedents = computed(() => historicalComparison.value?.precedents || [])

const hasQuantData = computed(() => {
  return !!(escalationData.value || stanceData.value || riskMatrixData.value || stakeholderData.value)
})

const verdictClass = computed(() => {
  const v = (decisionPayload.value?.verdict || '').toLowerCase().trim()
  if (/\bno[- ]?go\b/.test(v)) return 'verdict-nogo'
  if (/\bgo\b/.test(v)) return 'verdict-go'
  return 'verdict-caution'
})

const getHistBarHeight = (bin, histogram) => {
  if (!histogram?.length) return 0
  const maxCount = Math.max(...histogram.map(b => b.count || 0))
  return maxCount > 0 ? ((bin.count || 0) / maxCount) * 100 : 0
}

const getMcBarClass = (bin, cis) => {
  if (!cis) return 'mc-bar-default'
  const ci90 = cis['90%']
  const ci95 = cis['95%']
  const center = bin.center
  if (ci90 && center >= ci90[0] && center <= ci90[1]) return 'mc-bar-ci90'
  if (ci95 && center >= ci95[0] && center <= ci95[1]) return 'mc-bar-ci95'
  return 'mc-bar-tail'
}

const getCiBandStyle = (ci, mc) => {
  if (!ci || !mc?.histogram?.length) return {}
  const hist = mc.histogram
  const minVal = hist[0].min
  const maxVal = hist[hist.length - 1].max
  const range = maxVal - minVal || 1
  const left = ((ci[0] - minVal) / range) * 100
  const width = ((ci[1] - ci[0]) / range) * 100
  return { left: left + '%', width: width + '%' }
}

const getMeanMarkerStyle = (mc) => {
  if (!mc?.histogram?.length) return {}
  const hist = mc.histogram
  const minVal = hist[0].min
  const maxVal = hist[hist.length - 1].max
  const range = maxVal - minVal || 1
  return { left: ((mc.mean - minVal) / range) * 100 + '%' }
}

const getRiskCellClass = (likelihood, impact) => {
  const score = likelihood * impact
  if (score >= 16) return 'risk-critical'
  if (score >= 10) return 'risk-high'
  if (score >= 5) return 'risk-moderate'
  return 'risk-low'
}

const getRisksInCell = (likelihood, impact) => {
  if (!riskMatrixData.value?.risks) return []
  return riskMatrixData.value.risks.filter(r => r.likelihood === likelihood && r.impact === impact)
}

const startPolling = () => {
  if (agentLogTimer || consoleLogTimer) return
  
  fetchAgentLog()
  fetchConsoleLog()
  
  agentLogTimer = setInterval(fetchAgentLog, 2000)
  consoleLogTimer = setInterval(fetchConsoleLog, 1500)
}

const stopPolling = () => {
  if (agentLogTimer) {
    clearInterval(agentLogTimer)
    agentLogTimer = null
  }
  if (consoleLogTimer) {
    clearInterval(consoleLogTimer)
    consoleLogTimer = null
  }
}

// Lifecycle
onUnmounted(() => {
  stopPolling()
})

watch(() => props.reportId, (newId) => {
  stopPolling()
  if (newId) {
    agentLogs.value = []
    consoleLogs.value = []
    agentLogLine.value = 0
    consoleLogLine.value = 0
    reportOutline.value = null
    reportPayload.value = null
    currentSectionIndex.value = null
    generatedSections.value = {}
    expandedContent.value = new Set()
    expandedLogs.value = new Set()
    collapsedSections.value = new Set()
    isComplete.value = false
    startTime.value = null
    
    startPolling()
  }
}, { immediate: true })
</script>


<style scoped src="./Step4Report.scoped.css"></style>

