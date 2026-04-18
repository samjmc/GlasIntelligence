<template>
  <div class="env-setup-panel">
    <div class="scroll-container">
      <!-- Step 01: Simulation Instance -->
      <div class="step-card" :class="{ 'active': phase === 0, 'completed': phase > 0 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">01</span>
            <span class="step-title">Simulation Instance Initialization</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 0" class="badge success">Completed</span>
            <span v-else class="badge processing">Initializing</span>
          </div>
        </div>
        
        <div class="card-content">
          <p class="api-note">POST /api/simulation/create</p>
          <p class="description">
            Create simulation instance and fetch world parameter template
          </p>

          <div v-if="simulationId" class="info-card">
            <div class="info-row">
              <span class="info-label">Project ID</span>
              <span class="info-value mono">{{ projectData?.project_id }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Graph ID</span>
              <span class="info-value mono">{{ projectData?.graph_id }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Simulation ID</span>
              <span class="info-value mono">{{ simulationId }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Task ID</span>
              <span class="info-value mono">{{ taskId || 'Async task completed' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 02: Generate Agent Personas -->
      <div class="step-card" :class="{ 'active': phase === 1, 'completed': phase > 1 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">02</span>
            <span class="step-title">Generate Agent Personas</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 1" class="badge success">Completed</span>
            <span v-else-if="phase === 1" class="badge processing">{{ prepareProgress }}%</span>
            <span v-else class="badge pending">Waiting</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/simulation/prepare</p>
          <p class="description">
            Extract entities from knowledge graph, initialize agents with behavior and memory
          </p>

          <!-- Profiles Stats -->
          <div v-if="profiles.length > 0" class="stats-grid">
            <div class="stat-card">
              <span class="stat-value">{{ profiles.length }}</span>
              <span class="stat-label">Current Agents</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ expectedTotal || '-' }}</span>
              <span class="stat-label">Expected Total</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ totalTopicsCount }}</span>
              <span class="stat-label">Related Topics</span>
            </div>
          </div>

          <!-- Profiles List Preview -->
          <div v-if="profiles.length > 0" class="profiles-preview">
            <div class="preview-header">
              <span class="preview-title">Generated Agent Personas</span>
            </div>
            <div class="profiles-list">
              <div 
                v-for="(profile, idx) in profiles" 
                :key="idx" 
                class="profile-card"
                @click="selectProfile(profile)"
              >
                <div class="profile-header">
                  <span class="profile-realname">{{ profile.username || 'Unknown' }}</span>
                  <span class="profile-username">@{{ profile.name || `agent_${idx}` }}</span>
                </div>
                <div class="profile-meta">
                  <span class="profile-profession">{{ profile.profession || 'Unknown role' }}</span>
                </div>
                <p class="profile-bio">{{ profile.bio || 'No bio available' }}</p>
                <div v-if="profile.interested_topics?.length" class="profile-topics">
                  <span 
                    v-for="topic in profile.interested_topics.slice(0, 3)" 
                    :key="topic" 
                    class="topic-tag"
                  >{{ topic }}</span>
                  <span v-if="profile.interested_topics.length > 3" class="topic-more">
                    +{{ profile.interested_topics.length - 3 }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 03: Generate Simulation Config -->
      <div class="step-card" :class="{ 'active': phase === 2, 'completed': phase > 2 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">03</span>
            <span class="step-title">Generate Simulation Config</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 2" class="badge success">Completed</span>
            <span v-else-if="phase === 2" class="badge processing">Generating</span>
            <span v-else class="badge pending">Waiting</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/simulation/prepare</p>
          <p class="description">
            LLM configures time flow, agent activity, events, and platform parameters
          </p>
          
          <!-- Config Preview -->
          <div v-if="simulationConfig" class="config-detail-panel">
            <!-- Time Configuration -->
            <div class="config-block">
              <div class="config-grid">
                <div class="config-item">
                  <span class="config-item-label">Time Scale</span>
                  <span class="config-item-value">{{ timeScaleUnit }} per round</span>
                </div>
                <div class="config-item">
                  <span class="config-item-label">Simulation Duration</span>
                  <span class="config-item-value">{{ timeScaleDuration }}</span>
                </div>
                <div class="config-item">
                  <span class="config-item-label">Total Rounds</span>
                  <span class="config-item-value">{{ computedTotalRounds || '-' }} rounds</span>
                </div>
                <div class="config-item">
                  <span class="config-item-label">Active Per Round</span>
                  <span class="config-item-value">{{ simulationConfig.time_config?.agents_per_round_min ?? simulationConfig.time_config?.agents_per_hour_min }}-{{ simulationConfig.time_config?.agents_per_round_max ?? simulationConfig.time_config?.agents_per_hour_max }}</span>
                </div>
                <div v-if="timeScaleStartDate" class="config-item">
                  <span class="config-item-label">Start Date</span>
                  <span class="config-item-value">{{ timeScaleStartDate }}</span>
                </div>
              </div>

              <!-- Hour-based: show peak/off-peak periods -->
              <div v-if="isHourlyScale" class="time-periods">
                <div class="period-item">
                  <span class="period-label">Peak Hours</span>
                  <span class="period-hours">{{ simulationConfig.time_config?.peak_hours?.join(':00, ') }}:00</span>
                  <span class="period-multiplier">×{{ simulationConfig.time_config?.peak_activity_multiplier }}</span>
                </div>
                <div class="period-item">
                  <span class="period-label">Work Hours</span>
                  <span class="period-hours">{{ simulationConfig.time_config?.work_hours?.[0] }}:00-{{ simulationConfig.time_config?.work_hours?.slice(-1)[0] }}:00</span>
                  <span class="period-multiplier">×{{ simulationConfig.time_config?.work_activity_multiplier }}</span>
                </div>
                <div class="period-item">
                  <span class="period-label">Morning Hours</span>
                  <span class="period-hours">{{ simulationConfig.time_config?.morning_hours?.[0] }}:00-{{ simulationConfig.time_config?.morning_hours?.slice(-1)[0] }}:00</span>
                  <span class="period-multiplier">×{{ simulationConfig.time_config?.morning_activity_multiplier }}</span>
                </div>
                <div class="period-item">
                  <span class="period-label">Off-Peak Hours</span>
                  <span class="period-hours">{{ simulationConfig.time_config?.off_peak_hours?.[0] }}:00-{{ simulationConfig.time_config?.off_peak_hours?.slice(-1)[0] }}:00</span>
                  <span class="period-multiplier">×{{ simulationConfig.time_config?.off_peak_activity_multiplier }}</span>
                </div>
              </div>

              <!-- Coarse scale: show scenario phases -->
              <div v-else-if="scenarioPhases.length > 0" class="time-periods">
                <div v-for="(phase, idx) in scenarioPhases" :key="idx" class="period-item">
                  <span class="period-label">{{ phase.name }}</span>
                  <span class="period-hours">Rounds {{ phase.start_round }}–{{ phase.end_round }}</span>
                  <span class="period-multiplier">×{{ phase.activity_multiplier }}</span>
                </div>
              </div>
            </div>

            <!-- Agent Configuration -->
            <div class="config-block">
              <div class="config-block-header">
                <span class="config-block-title">Agent Configuration</span>
                <span class="config-block-badge">{{ simulationConfig.agent_configs?.length || 0 }}</span>
              </div>
              <div class="agents-cards">
                <div 
                  v-for="agent in simulationConfig.agent_configs" 
                  :key="agent.agent_id" 
                  class="agent-card"
                >
                  <div class="agent-card-header">
                    <div class="agent-identity">
                      <span class="agent-id">Agent {{ agent.agent_id }}</span>
                      <span class="agent-name">{{ agent.entity_name }}</span>
                    </div>
                    <div class="agent-tags">
                      <span class="agent-type">{{ agent.entity_type }}</span>
                      <span class="agent-stance" :class="'stance-' + agent.stance">{{ agent.stance }}</span>
                    </div>
                  </div>
                  
                  <div v-if="isHourlyScale" class="agent-timeline">
                    <span class="timeline-label">Active Hours</span>
                    <div class="mini-timeline">
                      <div 
                        v-for="hour in 24" 
                        :key="hour - 1" 
                        class="timeline-hour"
                        :class="{ 'active': agent.active_hours?.includes(hour - 1) }"
                        :title="`${hour - 1}:00`"
                      ></div>
                    </div>
                    <div class="timeline-marks">
                      <span>0</span>
                      <span>6</span>
                      <span>12</span>
                      <span>18</span>
                      <span>24</span>
                    </div>
                  </div>

                  <div class="agent-params">
                    <div class="param-group">
                      <div class="param-item">
                        <span class="param-label">Posts/rnd</span>
                        <span class="param-value">{{ agent.posts_per_round ?? agent.posts_per_hour }}</span>
                      </div>
                      <div class="param-item">
                        <span class="param-label">Comments/rnd</span>
                        <span class="param-value">{{ agent.comments_per_round ?? agent.comments_per_hour }}</span>
                      </div>
                      <div class="param-item">
                        <span class="param-label">Response Delay</span>
                        <span class="param-value">{{ agent.response_delay_min }}-{{ agent.response_delay_max }}min</span>
                      </div>
                    </div>
                    <div class="param-group">
                      <div class="param-item">
                        <span class="param-label">Activity Level</span>
                        <span class="param-value with-bar">
                          <span class="mini-bar" :style="{ width: (agent.activity_level * 100) + '%' }"></span>
                          {{ (agent.activity_level * 100).toFixed(0) }}%
                        </span>
                      </div>
                      <div class="param-item">
                        <span class="param-label">Sentiment</span>
                        <span class="param-value" :class="agent.sentiment_bias > 0 ? 'positive' : agent.sentiment_bias < 0 ? 'negative' : 'neutral'">
                          {{ agent.sentiment_bias > 0 ? '+' : '' }}{{ agent.sentiment_bias?.toFixed(1) }}
                        </span>
                      </div>
                      <div class="param-item">
                        <span class="param-label">Influence</span>
                        <span class="param-value highlight">{{ agent.influence_weight?.toFixed(1) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="config-block">
              <div class="config-block-header">
                <span class="config-block-title">Recommendation Algorithm Config</span>
              </div>
              <div class="platforms-grid">
                <div v-if="simulationConfig.twitter_config" class="platform-card">
                  <div class="platform-card-header">
                    <span class="platform-name">Platform 1: Feed / Timeline</span>
                  </div>
                  <div class="platform-params">
                    <div class="param-row">
                      <span class="param-label">Recency Weight</span>
                      <span class="param-value">{{ simulationConfig.twitter_config.recency_weight }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">Popularity Weight</span>
                      <span class="param-value">{{ simulationConfig.twitter_config.popularity_weight }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">Relevance Weight</span>
                      <span class="param-value">{{ simulationConfig.twitter_config.relevance_weight }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">Viral Threshold</span>
                      <span class="param-value">{{ simulationConfig.twitter_config.viral_threshold }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">Echo Chamber Strength</span>
                      <span class="param-value">{{ simulationConfig.twitter_config.echo_chamber_strength }}</span>
                    </div>
                  </div>
                </div>
                <div v-if="simulationConfig.reddit_config" class="platform-card">
                  <div class="platform-card-header">
                    <span class="platform-name">Platform 2: Forum / Community</span>
                  </div>
                  <div class="platform-params">
                    <div class="param-row">
                      <span class="param-label">Recency Weight</span>
                      <span class="param-value">{{ simulationConfig.reddit_config.recency_weight }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">Popularity Weight</span>
                      <span class="param-value">{{ simulationConfig.reddit_config.popularity_weight }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">Relevance Weight</span>
                      <span class="param-value">{{ simulationConfig.reddit_config.relevance_weight }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">Viral Threshold</span>
                      <span class="param-value">{{ simulationConfig.reddit_config.viral_threshold }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">Echo Chamber Strength</span>
                      <span class="param-value">{{ simulationConfig.reddit_config.echo_chamber_strength }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="simulationConfig.generation_reasoning" class="config-block">
              <div class="config-block-header">
                <span class="config-block-title">LLM Config Reasoning</span>
              </div>
              <div class="reasoning-content">
                <div 
                  v-for="(reason, idx) in simulationConfig.generation_reasoning.split('|').slice(0, 2)" 
                  :key="idx" 
                  class="reasoning-item"
                >
                  <p class="reasoning-text">{{ reason.trim() }}</p>
                </div>
              </div>
            </div>
          </div>

          <div v-if="prepareWarnings.length > 0" class="prepare-warnings">
            <div v-for="(w, idx) in prepareWarnings" :key="idx" class="prepare-warning-item">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
              <span>{{ w }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 04: Initial Activation -->
      <div class="step-card" :class="{ 'active': phase === 3, 'completed': phase > 3 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">04</span>
            <span class="step-title">Initial Activation</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 3" class="badge success">Completed</span>
            <span v-else-if="phase === 3" class="badge processing">Orchestrating</span>
            <span v-else class="badge pending">Waiting</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/simulation/prepare</p>
          <p class="description">
            Generate initial activation events and hot topics based on narrative direction to seed the simulation
          </p>

          <div v-if="simulationConfig?.event_config" class="orchestration-content">
            <div class="narrative-box">
              <span class="box-label narrative-label">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="special-icon">
                  <path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" stroke="url(#paint0_linear)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                  <path d="M16.24 7.76L14.12 14.12L7.76 16.24L9.88 9.88L16.24 7.76Z" fill="url(#paint0_linear)" stroke="url(#paint0_linear)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                  <defs>
                    <linearGradient id="paint0_linear" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
                      <stop stop-color="#FF5722"/>
                      <stop offset="1" stop-color="#FF9800"/>
                    </linearGradient>
                  </defs>
                </svg>
                Narrative Direction
              </span>
              <p class="narrative-text">{{ simulationConfig.event_config.narrative_direction }}</p>
            </div>

            <div class="topics-section">
              <span class="box-label">Initial Hot Topics</span>
              <div class="hot-topics-grid">
                <span v-for="topic in simulationConfig.event_config.hot_topics" :key="topic" class="hot-topic-tag">
                  # {{ topic }}
                </span>
              </div>
            </div>

            <div class="initial-posts-section">
              <span class="box-label">Initial Activation Sequence ({{ simulationConfig.event_config.initial_posts.length }})</span>
              <div class="posts-timeline">
                <div v-for="(post, idx) in simulationConfig.event_config.initial_posts" :key="idx" class="timeline-item">
                  <div class="timeline-marker"></div>
                  <div class="timeline-content">
                    <div class="post-header">
                      <span class="post-role">{{ post.poster_type }}</span>
                      <span class="post-agent-info">
                        <span class="post-id">Agent {{ post.poster_agent_id }}</span>
                        <span class="post-username">@{{ getAgentUsername(post.poster_agent_id) }}</span>
                      </span>
                    </div>
                    <p class="post-text">{{ post.content }}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 05: Preparation Complete -->
      <div class="step-card" :class="{ 'active': phase === 4 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">05</span>
            <span class="step-title">Preparation Complete</span>
          </div>
          <div class="step-status">
            <span v-if="phase >= 4" class="badge processing">In Progress</span>
            <span v-else class="badge pending">Waiting</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/simulation/start</p>
          <p class="description">Environment ready. You can start the simulation.</p>
          
          <div v-if="simulationConfig" class="rounds-config-section">
            <div class="rounds-header">
              <div class="header-left">
                <span class="section-title">Simulation Parameters</span>
                <span class="section-desc" v-if="!isEnterprise">
                  Fixed for your <span class="desc-highlight">{{ userPlan }}</span> plan — {{ planAgentLimit }} agents, {{ planRoundLimit }} rounds
                </span>
                <span class="section-desc" v-else>
                  Enterprise: <span class="desc-highlight">{{ timeScaleDuration }}</span>; each round = <span class="desc-highlight">1 {{ timeScaleUnit }}</span>
                </span>
              </div>
              <label v-if="isEnterprise" class="switch-control">
                <input type="checkbox" v-model="useCustomRounds">
                <span class="switch-track"></span>
                <span class="switch-label">Custom</span>
              </label>
            </div>
            
            <Transition name="fade" mode="out-in">
              <!-- Enterprise custom mode -->
              <div v-if="isEnterprise && useCustomRounds" class="rounds-content custom" key="custom">
                <div class="slider-display">
                  <div class="slider-main-value">
                    <span class="val-num">{{ customMaxRounds }}</span>
                    <span class="val-unit">rounds</span>
                  </div>
                  <div class="slider-meta-info">
                    <span>With 100 agents: estimated {{ Math.round(customMaxRounds * 0.6) }} min</span>
                  </div>
                </div>

                <div class="range-wrapper">
                  <input 
                    type="range" 
                    v-model.number="customMaxRounds" 
                    min="10" 
                    :max="autoGeneratedRounds || 200"
                    step="5"
                    class="minimal-slider"
                    :style="{ '--percent': ((customMaxRounds - 10) / ((autoGeneratedRounds || 200) - 10)) * 100 + '%' }"
                  />
                  <div class="range-marks">
                    <span>10</span>
                    <span 
                      class="mark-recommend" 
                      :class="{ active: customMaxRounds === 40 }"
                      @click="customMaxRounds = 40"
                      :style="{ position: 'absolute', left: `calc(${(40 - 10) / ((autoGeneratedRounds || 200) - 10) * 100}% - 30px)` }"
                    >40 (recommended)</span>
                    <span>{{ autoGeneratedRounds || 200 }}</span>
                  </div>
                </div>
              </div>
              
              <!-- Fixed plan display (Pro / Business) or Enterprise auto mode -->
              <div v-else class="rounds-content auto" key="auto">
                <div class="auto-info-card">
                  <div class="auto-value">
                    <span class="val-num">{{ effectiveRounds }}</span>
                    <span class="val-unit">rounds</span>
                  </div>
                  <div class="auto-content">
                    <div class="auto-meta-row">
                      <span class="plan-badge" v-if="!isEnterprise">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                        </svg>
                        {{ { pro: 'Pro', business: 'Business', payg: 'Pay-as-you-go', free: 'Free' }[userPlan] || userPlan }} plan: {{ planAgentLimit }} agents, {{ planRoundLimit }} rounds per simulation
                      </span>
                      <span class="duration-badge" v-else>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <circle cx="12" cy="12" r="10"></circle>
                          <polyline points="12 6 12 12 16 14"></polyline>
                        </svg>
                        Estimated {{ Math.round((autoGeneratedRounds || 40) * 0.6) }} min
                      </span>
                    </div>
                    <div class="auto-desc" v-if="!isEnterprise">
                      <p class="plan-info-tip">Upgrade to Enterprise for custom agent and round configuration</p>
                    </div>
                  </div>
                </div>
              </div>
            </Transition>
          </div>

          <div class="action-group dual">
            <button 
              class="action-btn secondary"
              @click="$emit('go-back')"
            >
              ← Back to Knowledge Graph
            </button>
            <button 
              class="action-btn primary"
              :disabled="phase < 4"
              @click="openTimelineConfirm"
            >
              Start Simulation ➝
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Confirm timeline before run -->
    <Transition name="modal">
      <div
        v-if="showTimelineConfirm"
        class="timeline-confirm-overlay"
        @click.self="showTimelineConfirm = false"
      >
        <div class="timeline-confirm-modal" role="dialog" aria-labelledby="timeline-confirm-title">
          <div class="timeline-confirm-header">
            <h3 id="timeline-confirm-title">Confirm time scale &amp; rounds</h3>
            <button type="button" class="close-btn" aria-label="Close" @click="showTimelineConfirm = false">×</button>
          </div>
          <p class="timeline-confirm-intro">
            The engine steps through discrete rounds. Adjust how much simulated time each round covers and how many rounds run
            (your plan still applies a maximum).
          </p>

          <div class="timeline-mode-toggle">
            <label class="mode-option">
              <input v-model="timelineModeHour" type="radio" :value="true" />
              <span>Compressed (hours / minutes per round)</span>
            </label>
            <label class="mode-option">
              <input v-model="timelineModeHour" type="radio" :value="false" />
              <span>Calendar (days, weeks, months, years)</span>
            </label>
          </div>

          <div v-if="timelineModeHour" class="timeline-fields">
            <label class="tf-row">
              <span>Total simulated hours</span>
              <input v-model.number="confirmTotalHours" type="number" min="1" max="8760" class="tf-input" />
            </label>
            <label class="tf-row">
              <span>Minutes per round</span>
              <input v-model.number="confirmMinutesPerRound" type="number" min="1" max="1440" class="tf-input" />
            </label>
            <p class="timeline-preview mono">
              ≈ {{ previewRoundsFromHour }} rounds (before plan cap)
            </p>
          </div>

          <div v-else class="timeline-fields">
            <label class="tf-row">
              <span>Time unit</span>
              <select v-model="confirmUnit" class="tf-input">
                <option value="day">Day</option>
                <option value="week">Week</option>
                <option value="month">Month</option>
                <option value="year">Year</option>
              </select>
            </label>
            <label class="tf-row">
              <span>Simulated time per round (in that unit)</span>
              <input v-model.number="confirmPerRound" type="number" min="1" max="520" class="tf-input" />
            </label>
            <label class="tf-row">
              <span>Number of rounds</span>
              <input v-model.number="confirmNumRounds" type="number" min="1" max="500" class="tf-input" />
            </label>
            <p class="timeline-preview mono">
              Span: {{ confirmNumRounds * confirmPerRound }} {{ confirmUnit }}(s) ·
              {{ previewRoundsCalendar }} rounds (before plan cap)
            </p>
          </div>

          <p v-if="planRoundLimit" class="timeline-plan-note">
            Your plan allows up to <strong>{{ planRoundLimit }}</strong> rounds per run; longer timelines may be truncated.
          </p>

          <div class="timeline-confirm-actions">
            <button type="button" class="action-btn secondary" @click="showTimelineConfirm = false">Cancel</button>
            <button type="button" class="action-btn primary" @click="confirmTimelineAndStart">Confirm &amp; continue</button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Profile Detail Modal -->
    <Transition name="modal">
      <div v-if="selectedProfile" class="profile-modal-overlay" @click.self="selectedProfile = null">
        <div class="profile-modal">
          <div class="modal-header">
          <div class="modal-header-info">
            <div class="modal-name-row">
              <span class="modal-realname">{{ selectedProfile.username }}</span>
              <span class="modal-username">@{{ selectedProfile.name }}</span>
            </div>
            <span class="modal-profession">{{ selectedProfile.profession }}</span>
          </div>
          <button class="close-btn" @click="selectedProfile = null">×</button>
        </div>
        
        <div class="modal-body">
          <div class="modal-info-grid">
            <div class="info-item">
              <span class="info-label">Age</span>
              <span class="info-value">{{ selectedProfile.age || '-' }} years</span>
            </div>
            <div class="info-item">
              <span class="info-label">Gender</span>
              <span class="info-value">{{ { male: 'Male', female: 'Female', other: 'Other' }[selectedProfile.gender] || selectedProfile.gender }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">Country/Region</span>
              <span class="info-value">{{ selectedProfile.country || '-' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">MBTI</span>
              <span class="info-value mbti">{{ selectedProfile.mbti || '-' }}</span>
            </div>
          </div>

          <div class="modal-section">
            <span class="section-label">Persona Summary</span>
            <p class="section-bio">{{ selectedProfile.bio || 'No bio available' }}</p>
          </div>

          <div class="modal-section" v-if="selectedProfile.interested_topics?.length">
            <span class="section-label">Related Topics</span>
            <div class="topics-grid">
              <span 
                v-for="topic in selectedProfile.interested_topics" 
                :key="topic" 
                class="topic-item"
              >{{ topic }}</span>
            </div>
          </div>

          <div class="modal-section" v-if="selectedProfile.persona">
            <span class="section-label">Detailed Persona Background</span>
            
            <div class="persona-dimensions">
              <div class="dimension-card">
                <span class="dim-title">Event Overview</span>
                <span class="dim-desc">Complete behavioral trajectory in this event</span>
              </div>
              <div class="dimension-card">
                <span class="dim-title">Behavioral Profile</span>
                <span class="dim-desc">Experience summary and behavioral preferences</span>
              </div>
              <div class="dimension-card">
                <span class="dim-title">Memory Imprint</span>
                <span class="dim-desc">Memories formed from reality seeds</span>
              </div>
              <div class="dimension-card">
                <span class="dim-title">Social Network</span>
                <span class="dim-desc">Individual connections and interaction graph</span>
              </div>
            </div>

            <div class="persona-content">
              <p class="section-persona">{{ selectedProfile.persona }}</p>
            </div>
          </div>
        </div>
      </div>
      </div>
    </Transition>

    <!-- Bottom Info / Logs -->
    <div class="system-logs">
      <div class="log-header">
        <span class="log-title">SYSTEM DASHBOARD</span>
        <span class="log-id">{{ simulationId || 'NO_SIMULATION' }}</span>
      </div>
      <div class="log-content" ref="logContent">
        <div class="log-line" v-for="(log, idx) in systemLogs" :key="idx">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { 
  prepareSimulation, 
  getPrepareStatus, 
  getSimulationProfilesRealtime,
  getSimulationConfig,
  getSimulationConfigRealtime 
} from '../api/simulation'
import { createAdaptiveStepPoll } from '../composables/useAdaptiveStepPolling'

const props = defineProps({
  simulationId: String,
  projectData: Object,
  graphData: Object,
  systemLogs: Array,
  userPlan: { type: String, default: 'free' }
})

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status'])

// State
const phase = ref(0)
const taskId = ref(null)
const prepareProgress = ref(0)
const currentStage = ref('')
const progressMessage = ref('')
const profiles = ref([])
const entityTypes = ref([])
const expectedTotal = ref(null)
const simulationConfig = ref(null)
const prepareWarnings = ref([])
const selectedProfile = ref(null)
const showProfilesDetail = ref(true)

let lastLoggedMessage = ''
let lastLoggedProfileCount = 0
let lastLoggedConfigStage = ''

const useCustomRounds = ref(false)
const customMaxRounds = ref(40)

const showTimelineConfirm = ref(false)
const timelineModeHour = ref(true)
const confirmTotalHours = ref(72)
const confirmMinutesPerRound = ref(60)
const confirmUnit = ref('month')
const confirmPerRound = ref(1)
const confirmNumRounds = ref(6)

const isEnterprise = computed(() => props.userPlan === 'enterprise')

const planRoundLimit = computed(() => {
  if (props.userPlan === 'business') return 30
  if (props.userPlan === 'pro' || props.userPlan === 'payg') return 25
  if (props.userPlan === 'free') return 15
  return null // enterprise = no fixed cap
})

const planAgentLimit = computed(() => {
  if (props.userPlan === 'business') return 75
  if (props.userPlan === 'pro' || props.userPlan === 'payg') return 50
  if (props.userPlan === 'free') return 25
  return null
})

const effectiveRounds = computed(() => {
  if (isEnterprise.value) {
    return useCustomRounds.value ? customMaxRounds.value : autoGeneratedRounds.value
  }
  return planRoundLimit.value || autoGeneratedRounds.value
})

// Watch stage to update phase
watch(currentStage, (newStage) => {
  if (newStage === 'Generating Agent Personas' || newStage === 'generating_profiles') {
    phase.value = 1
  } else if (newStage === 'Generating Simulation Config' || newStage === 'generating_config') {
    phase.value = 2
    if (!configPoll.isActive) {
      addLog('Generating simulation config...')
      startConfigPolling()
    }
  } else if (newStage === 'Preparing Simulation Scripts' || newStage === 'copying_scripts') {
    phase.value = 2
  }
})

const timeScale = computed(() => simulationConfig.value?.time_config?.time_scale || { unit: 'hour', per_round: 1 })
const isHourlyScale = computed(() => (timeScale.value.unit || 'hour') === 'hour')
const timeScaleUnit = computed(() => {
  const u = timeScale.value.unit || 'hour'
  const pr = timeScale.value.per_round || 1
  if (pr === 1) return u
  return `${pr} ${u}s`
})
const timeScaleDuration = computed(() => {
  if (isHourlyScale.value) {
    return `${simulationConfig.value?.time_config?.total_simulation_hours || '-'} hours`
  }
  const dur = timeScale.value.total_duration || '-'
  const u = timeScale.value.unit || 'unit'
  return `${dur} ${u}s`
})
const timeScaleStartDate = computed(() => timeScale.value.start_date || '')
const scenarioPhases = computed(() => simulationConfig.value?.time_config?.phases || [])
const computedTotalRounds = computed(() => {
  if (!simulationConfig.value?.time_config) return null
  if (!isHourlyScale.value) {
    const dur = timeScale.value.total_duration || 0
    const pr = Math.max(timeScale.value.per_round || 1, 1)
    return Math.floor(dur / pr)
  }
  const totalHours = simulationConfig.value.time_config.total_simulation_hours
  const minutesPerRound = simulationConfig.value.time_config.minutes_per_round
  if (!totalHours || !minutesPerRound) return null
  return Math.floor((totalHours * 60) / minutesPerRound)
})

const autoGeneratedRounds = computed(() => {
  const r = computedTotalRounds.value
  if (!r) return null
  return Math.max(r, 40)
})

const previewRoundsFromHour = computed(() => {
  const h = Math.max(1, Number(confirmTotalHours.value) || 1)
  const m = Math.max(1, Number(confirmMinutesPerRound.value) || 1)
  return Math.max(1, Math.floor((h * 60) / m))
})

const previewRoundsCalendar = computed(() => {
  return Math.max(1, Math.floor(Number(confirmNumRounds.value) || 1))
})

const preparePoll = createAdaptiveStepPoll()
const profilesPoll = createAdaptiveStepPoll()
const configPoll = createAdaptiveStepPoll()

// Computed
const displayProfiles = computed(() => {
  if (showProfilesDetail.value) {
    return profiles.value
  }
  return profiles.value.slice(0, 6)
})

const getAgentUsername = (agentId) => {
  if (profiles.value && profiles.value.length > agentId && agentId >= 0) {
    const profile = profiles.value[agentId]
    return profile?.username || `agent_${agentId}`
  }
  return `agent_${agentId}`
}

const totalTopicsCount = computed(() => {
  return profiles.value.reduce((sum, p) => {
    return sum + (p.interested_topics?.length || 0)
  }, 0)
})

// Methods
const addLog = (msg) => {
  emit('add-log', msg)
}

function openTimelineConfirm() {
  const tc = simulationConfig.value?.time_config || {}
  const ts = tc.time_scale || {}
  const u = ts.unit || 'hour'
  if (u === 'hour') {
    timelineModeHour.value = true
    confirmTotalHours.value = Math.max(1, tc.total_simulation_hours || 72)
    confirmMinutesPerRound.value = Math.max(1, tc.minutes_per_round || 60)
  } else {
    timelineModeHour.value = false
    confirmUnit.value = ['day', 'week', 'month', 'year'].includes(u) ? u : 'month'
    confirmPerRound.value = Math.max(1, ts.per_round || 1)
    const dur = Math.max(0, ts.total_duration || 0)
    const pr = confirmPerRound.value
    confirmNumRounds.value = Math.max(1, pr > 0 ? Math.floor(dur / pr) : 6)
  }
  showTimelineConfirm.value = true
}

function confirmTimelineAndStart() {
  let timeConfig = {}
  if (timelineModeHour.value) {
    timeConfig = {
      total_simulation_hours: Math.max(1, Math.min(8760, Number(confirmTotalHours.value) || 72)),
      minutes_per_round: Math.max(1, Math.min(1440, Number(confirmMinutesPerRound.value) || 60)),
      time_scale: { unit: 'hour', per_round: 1, total_duration: 0 },
    }
  } else {
    const pr = Math.max(1, Math.min(520, Number(confirmPerRound.value) || 1))
    const nr = Math.max(1, Math.min(500, Number(confirmNumRounds.value) || 1))
    const prevStart = simulationConfig.value?.time_config?.time_scale?.start_date
    timeConfig = {
      time_scale: {
        unit: confirmUnit.value,
        per_round: pr,
        total_duration: nr * pr,
        ...(prevStart ? { start_date: prevStart } : {}),
      },
    }
  }
  showTimelineConfirm.value = false
  addLog(`Timeline confirmed for run (${timelineModeHour.value ? 'hour' : 'calendar'} scale)`)
  emit('next-step', { maxRounds: effectiveRounds.value, timeConfig })
}

const truncateBio = (bio) => {
  if (bio.length > 80) {
    return bio.substring(0, 80) + '...'
  }
  return bio
}

const selectProfile = (profile) => {
  selectedProfile.value = profile
}

const startPrepareSimulation = async () => {
  if (!props.simulationId) {
    addLog('Error: missing simulationId')
    emit('update-status', 'error')
    return
  }
  
  phase.value = 1
  addLog(`Simulation instance created: ${props.simulationId}`)
  addLog('Preparing simulation environment...')
  emit('update-status', 'processing')
  
  try {
    const res = await prepareSimulation({
      simulation_id: props.simulationId,
      use_llm_for_profiles: true,
      parallel_profile_count: 5
    })
    
    if (res.success && res.data) {
      if (res.data.already_prepared) {
        addLog('Detected existing preparation data, loading directly')
        await loadPreparedData()
        return
      }
      
      taskId.value = res.data.task_id
      addLog(`Preparation task started`)
      addLog(`  └─ Task ID: ${res.data.task_id}`)
      
      if (res.data.expected_entities_count) {
        expectedTotal.value = res.data.expected_entities_count
        addLog(`Read ${res.data.expected_entities_count} entities from Zep graph`)
        if (res.data.entity_types && res.data.entity_types.length > 0) {
          addLog(`  └─ Entity types: ${res.data.entity_types.join(', ')}`)
        }
      }
      
      addLog('Polling preparation progress...')
      startPolling()
      startProfilesPolling()
    } else {
      addLog(`Preparation failed: ${res.error || 'Unknown error'}`)
      emit('update-status', 'error')
    }
  } catch (err) {
    addLog(`Preparation exception: ${err.message}`)
    emit('update-status', 'error')
  }
}

const startPolling = () => {
  preparePoll.stop()
  preparePoll.start(() => pollPrepareStatus())
}

const stopPolling = () => preparePoll.stop()

const startProfilesPolling = () => {
  profilesPoll.stop()
  profilesPoll.start(() => fetchProfilesRealtime())
}

const stopProfilesPolling = () => profilesPoll.stop()

const pollPrepareStatus = async () => {
  if (!taskId.value && !props.simulationId) return
  
  try {
    const res = await getPrepareStatus({
      task_id: taskId.value,
      simulation_id: props.simulationId
    })
    
    if (res.success && res.data) {
      const data = res.data
      
      prepareProgress.value = data.progress || 0
      progressMessage.value = data.message || ''
      
      if (data.progress_detail) {
        currentStage.value = data.progress_detail.current_stage_name || ''
        
        const detail = data.progress_detail
        const logKey = `${detail.current_stage}-${detail.current_item}-${detail.total_items}`
        if (logKey !== lastLoggedMessage && detail.item_description) {
          lastLoggedMessage = logKey
          const stageInfo = `[${detail.stage_index}/${detail.total_stages}]`
          if (detail.total_items > 0) {
            addLog(`${stageInfo} ${detail.current_stage_name}: ${detail.current_item}/${detail.total_items} - ${detail.item_description}`)
          } else {
            addLog(`${stageInfo} ${detail.current_stage_name}: ${detail.item_description}`)
          }
        }
      } else if (data.message) {
        const match = data.message.match(/\[(\d+)\/(\d+)\]\s*([^:]+)/)
        if (match) {
          currentStage.value = match[3].trim()
        }
        if (data.message !== lastLoggedMessage) {
          lastLoggedMessage = data.message
          addLog(data.message)
        }
      }
      
      if (data.status === 'completed' || data.status === 'ready' || data.already_prepared) {
        addLog('✓ Preparation complete')
        stopPolling()
        stopProfilesPolling()
        await loadPreparedData()
      } else if (data.status === 'failed') {
        addLog(`✗ Preparation failed: ${data.error || 'Unknown error'}`)
        stopPolling()
        stopProfilesPolling()
      }
    }
  } catch (err) {
    console.warn('Poll status failed:', err)
  }
}

const fetchProfilesRealtime = async () => {
  if (!props.simulationId) return
  
  try {
    const res = await getSimulationProfilesRealtime(props.simulationId, 'reddit')
    
    if (res.success && res.data) {
      const prevCount = profiles.value.length
      profiles.value = res.data.profiles || []
      if (res.data.total_expected) {
        expectedTotal.value = res.data.total_expected
      }
      
     
      const types = new Set()
      profiles.value.forEach(p => {
        if (p.entity_type) types.add(p.entity_type)
      })
      entityTypes.value = Array.from(types)
      
      const currentCount = profiles.value.length
      if (currentCount > 0 && currentCount !== lastLoggedProfileCount) {
        lastLoggedProfileCount = currentCount
        const total = expectedTotal.value || '?'
        const latestProfile = profiles.value[currentCount - 1]
        const profileName = latestProfile?.name || latestProfile?.username || `Agent_${currentCount}`
        if (currentCount === 1) {
          addLog(`Generating agent personas...`)
        }
        addLog(`→ Agent persona ${currentCount}/${total}: ${profileName} (${latestProfile?.profession || 'Unknown role'})`)
        
        if (expectedTotal.value && currentCount >= expectedTotal.value) {
          addLog(`✓ All ${currentCount} agent personas generated`)
        }
      }
    }
  } catch (err) {
    console.warn('Fetch profiles failed:', err)
  }
}

const startConfigPolling = () => {
  configPoll.stop()
  configPoll.start(() => fetchConfigRealtime())
}

const stopConfigPolling = () => configPoll.stop()

const fetchConfigRealtime = async () => {
  if (!props.simulationId) return
  
  try {
    const res = await getSimulationConfigRealtime(props.simulationId)
    
    if (res.success && res.data) {
      const data = res.data
      
      if (data.generation_stage && data.generation_stage !== lastLoggedConfigStage) {
        lastLoggedConfigStage = data.generation_stage
        if (data.generation_stage === 'generating_profiles') {
          addLog('Generating agent persona config...')
        } else if (data.generation_stage === 'generating_config') {
          addLog('LLM generating simulation config parameters...')
        }
      }
      
      if (data.config_generated && data.config) {
        simulationConfig.value = data.config
        addLog('✓ Simulation config generated')
        
        if (data.summary) {
          addLog(`  ├─ Agents: ${data.summary.total_agents}`)
          const ts = data.config?.time_config?.time_scale
          if (ts && ts.unit !== 'hour') {
            addLog(`  ├─ Duration: ${ts.total_duration} ${ts.unit}s`)
          } else {
            addLog(`  ├─ Duration: ${data.summary.simulation_hours} hours`)
          }
          addLog(`  ├─ Initial posts: ${data.summary.initial_posts_count}`)
          addLog(`  ├─ Hot topics: ${data.summary.hot_topics_count}`)
          addLog(`  └─ Platforms: Twitter ${data.summary.has_twitter_config ? '✓' : '✗'}, Reddit ${data.summary.has_reddit_config ? '✓' : '✗'}`)
        }
        
        if (data.config.time_config) {
          const tc = data.config.time_config
          const ts = tc.time_scale || { unit: 'hour', per_round: 1 }
          if (ts.unit !== 'hour') {
            addLog(`Time config: 1 ${ts.unit}/round, ${Math.floor((ts.total_duration || 0) / Math.max(ts.per_round || 1, 1))} rounds over ${ts.total_duration} ${ts.unit}s`)
          } else {
            addLog(`Time config: ${tc.minutes_per_round}min/round, ${Math.floor((tc.total_simulation_hours * 60) / tc.minutes_per_round)} rounds total`)
          }
        }
        
        if (data.config.event_config?.narrative_direction) {
          const narrative = data.config.event_config.narrative_direction
          addLog(`Narrative direction: ${narrative.length > 50 ? narrative.substring(0, 50) + '...' : narrative}`)
        }
        
        configPoll.stop()
        phase.value = 4
        addLog('✓ Environment setup complete, ready to simulate')
        emit('update-status', 'completed')
      }
    }
  } catch (err) {
    console.warn('Fetch config failed:', err)
  }
}

const loadPreparedData = async () => {
  phase.value = 2
  addLog('Loading existing config data...')

  await fetchProfilesRealtime()
  addLog(`Loaded ${profiles.value.length} agent personas`)

  try {
    const res = await getSimulationConfigRealtime(props.simulationId)
    if (res.success && res.data) {
      if (res.data.config_generated && res.data.config) {
        simulationConfig.value = res.data.config
        addLog('✓ Simulation config loaded')
        
        if (res.data.summary) {
          addLog(`  ├─ Agents: ${res.data.summary.total_agents}`)
          const ts = res.data.config?.time_config?.time_scale
          if (ts && ts.unit !== 'hour') {
            addLog(`  ├─ Duration: ${ts.total_duration} ${ts.unit}s`)
          } else {
            addLog(`  ├─ Duration: ${res.data.summary.simulation_hours} hours`)
          }
          addLog(`  └─ Initial posts: ${res.data.summary.initial_posts_count}`)
        }

        if (res.data.warnings?.length) {
          prepareWarnings.value = res.data.warnings
          for (const w of res.data.warnings) {
            addLog(`⚠ ${w}`)
          }
        }
        
        addLog('✓ Environment setup complete, ready to simulate')
        phase.value = 4
        emit('update-status', 'completed')
      } else {
        addLog('Config generating, polling...')
        startConfigPolling()
      }
    }
  } catch (err) {
    addLog(`Load config failed: ${err.message}`)
    emit('update-status', 'error')
  }
}

// Scroll log to bottom
const logContent = ref(null)
watch(() => props.systemLogs?.length, () => {
  nextTick(() => {
    if (logContent.value) {
      logContent.value.scrollTop = logContent.value.scrollHeight
    }
  })
})

const onStep2Visibility = () => {
  if (document.hidden) return
  if (preparePoll.isActive) void pollPrepareStatus()
  if (profilesPoll.isActive) void fetchProfilesRealtime()
  if (configPoll.isActive) void fetchConfigRealtime()
}

onMounted(() => {
  document.addEventListener('visibilitychange', onStep2Visibility)
  if (props.simulationId) {
    addLog('Step2 environment setup initializing')
    startPrepareSimulation()
  }
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onStep2Visibility)
  stopPolling()
  stopProfilesPolling()
  stopConfigPolling()
})
</script>

<style scoped src="./Step2EnvSetup.scoped.css"></style>
