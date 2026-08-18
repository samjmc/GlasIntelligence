<template>
  <div class="landing">
    <!-- Hero -->
    <section class="hero">
      <div class="hero-inner">
        <img src="/glas-logo.png" alt="Glas Intelligence" class="hero-logo" />
        <p class="brand-name">GLAS INTELLIGENCE</p>
        <h1 class="hero-headline">Scenario Intelligence for Strategic Decision-Making</h1>
        <p class="hero-sub">
          Multi-agent AI simulation that shows you how complex stakeholder situations evolve.
          Describe a scenario, and our engine analyses the 50 most relevant stakeholders across 25 critical decision points.
        </p>
        <div class="hero-ctas">
          <router-link to="/signup" class="btn btn-primary">Get Started Free</router-link>
          <router-link to="/feed" class="btn btn-outline">Browse Simulations</router-link>
        </div>
      </div>
    </section>

    <!-- How It Works -->
    <section class="how-it-works">
      <h2 class="section-heading">How It Works</h2>
      <div class="steps-grid">
        <div class="step-card" v-for="step in steps" :key="step.num">
          <span class="step-num">{{ step.num }}</span>
          <h3 class="step-title">{{ step.title }}</h3>
          <p class="step-desc">{{ step.desc }}</p>
        </div>
      </div>
    </section>

    <!-- Industry Feed Preview -->
    <section class="feed-preview">
      <h2 class="section-heading">Latest Industry Intelligence</h2>
      <p v-if="demoError" data-test="demo-box-error" class="demo-error">{{ demoError }}</p>
      <div class="feed-grid">
        <template v-if="isDemoMode">
          <button
            v-for="s in demoScenarios"
            :key="s.id"
            class="feed-card demo-card"
            data-test="demo-box"
            :data-scenario-id="s.id"
            @click="launchDemo(s)"
          >
            <span class="feed-tag">Live demo</span>
            <h3 class="feed-title">{{ s.title }}</h3>
            <p class="feed-excerpt">{{ s.blurb }}</p>
            <span class="feed-date">Launch walkthrough →</span>
          </button>
        </template>
        <template v-else>
          <div class="feed-card" v-for="item in feedItems" :key="item.id">
            <span class="feed-tag">{{ item.tag }}</span>
            <h3 class="feed-title">{{ item.title }}</h3>
            <p class="feed-excerpt">{{ item.excerpt }}</p>
            <span class="feed-date">{{ item.date }}</span>
          </div>
        </template>
      </div>
      <router-link to="/feed" class="section-link">View All Reports →</router-link>
    </section>

    <!-- Pricing Preview -->
    <section class="pricing-preview">
      <h2 class="section-heading">Pricing</h2>
      <div class="pricing-grid">
        <div class="pricing-card" v-for="plan in plans" :key="plan.name" :class="{ featured: plan.featured }">
          <h3 class="plan-name">{{ plan.name }}</h3>
          <p class="plan-price">{{ plan.price }}</p>
          <p class="plan-desc">{{ plan.desc }}</p>
        </div>
      </div>
      <router-link to="/pricing" class="section-link">View Full Pricing →</router-link>
    </section>

    <!-- Footer -->
    <footer class="landing-footer">
      <div class="footer-inner">
        <p class="footer-brand">GLAS INTELLIGENCE</p>
        <nav class="footer-links">
          <router-link to="/pricing">Pricing</router-link>
          <router-link to="/feed">Feed</router-link>
          <router-link to="/login">Login</router-link>
          <router-link to="/signup">Sign Up</router-link>
        </nav>
        <p class="footer-disclaimer">
          Glas Intelligence provides structured scenario analysis.
          It does not issue forecasts or policy recommendations.
        </p>
        <p class="footer-copy">&copy; 2026 Glas Intelligence</p>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { isDemoMode, SESSION_KEY } from '../demo/config'
import { encodeDemoId } from '../demo/sessionId'
import { setActiveScenario } from '../demo/adapter'
import { SCHEMA_VERSION } from '../demo/tape'

const router = useRouter()
const demoScenarios = ref([])
const demoError = ref('')

async function fetchManifest() {
  // One retry: same policy as DemoScenarioPicker and tape.js loadTape() — a CDN
  // hiccup on a static asset is usually transient. A second failure is real and
  // must surface.
  let res
  try {
    res = await fetch('/demo/manifest.json')
    if (!res.ok) throw new Error(`manifest ${res.status}`)
  } catch {
    res = await fetch('/demo/manifest.json')
    if (!res.ok) throw new Error(`manifest ${res.status}`)
  }
  const manifest = await res.json()
  if (manifest.schema_version !== SCHEMA_VERSION) {
    throw new Error(
      `Demo manifest schema ${manifest.schema_version} does not match expected ${SCHEMA_VERSION}`,
    )
  }
  return manifest
}

onMounted(async () => {
  if (!isDemoMode) return
  try {
    const manifest = await fetchManifest()
    demoScenarios.value = manifest.scenarios
  } catch (e) {
    demoError.value = e?.message || 'Demo failed to load. Please reload the page.'
  }
})

function launchDemo(s) {
  // The session id is minted at the moment the run starts (here, on click), so
  // that the virtual clock starts exactly when the run begins — not at page
  // load. At 20x speedup even a 5 s gap between render and click would burn
  // 100 s of tape and skip straight to the completed state.
  let sessionId
  try {
    sessionId = encodeDemoId(Date.now(), s.id)
    // Store before navigation so adapter.js can rehydrate on a page reload.
    localStorage.setItem(SESSION_KEY, sessionId)
  } catch (e) {
    // e.g. a scenario id containing '_' (encodeDemoId throws) or storage
    // unavailable (Safari private mode). Surface it rather than silently
    // swallowing the click.
    demoError.value = e?.message || 'Could not start this demo. Please reload the page.'
    return
  }
  setActiveScenario(s.id, sessionId)
  router.push({ name: 'SimulationRun', params: { simulationId: `demo-${s.id}-sim` } })
}

const steps = [
  {
    num: '01',
    title: 'Describe Your Scenario',
    desc: 'Tell us what you want to simulate — a regulation change, market shift, or geopolitical event.',
  },
  {
    num: '02',
    title: 'Gather Source Materials',
    desc: 'Our AI suggests the best documents to upload. Paid users can auto-generate a research briefing.',
  },
  {
    num: '03',
    title: 'Get Your Report',
    desc: 'Up to 50 stakeholder agents simulate reactions across 25 decision points. You get a detailed analysis report.',
  },
]

const feedItems = [
  {
    id: 1,
    tag: 'Energy',
    title: 'Impact of Removing the UK Energy Price Cap',
    excerpt: 'A multi-agent simulation exploring how suppliers, regulators, and consumers react to deregulated pricing.',
    date: 'Mar 2026',
  },
  {
    id: 2,
    tag: 'Finance',
    title: 'Basel IV Implementation: Stakeholder Dynamics',
    excerpt: 'How banks, fintechs, and supervisory bodies adapt to new capital requirements over 18 months.',
    date: 'Feb 2026',
  },
  {
    id: 3,
    tag: 'Geopolitics',
    title: 'US-Iran Nuclear Conflict: 9-Scenario Impact Analysis',
    excerpt: 'Multi-agent simulation of military strike options on Iranian nuclear facilities. Quantified outcomes across economic, social, and security dimensions.',
    date: 'Jan 2026',
  },
]

const plans = [
  { name: 'Free', price: '$0', desc: '1 pre-built simulation per month', featured: false },
  { name: 'Pro', price: '$99/mo', desc: '10 simulations + all industry feeds + PDF downloads', featured: true },
  { name: 'Business', price: '$299/mo', desc: '40 simulations + advanced scenario stacking + priority support', featured: false },
]
</script>

<style scoped>
.landing {
  min-height: 100vh;
  background: #0a0a0a;
  color: #e0e0e0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* ── Hero ────────────────────────────────── */

.hero {
  padding: 100px 24px 80px;
  text-align: center;
  background: radial-gradient(ellipse at 50% 0%, #111 0%, #0a0a0a 70%);
}

.hero-inner {
  max-width: 720px;
  margin: 0 auto;
}

.hero-logo {
  height: 72px;
  width: auto;
  margin-bottom: 24px;
  border-radius: 12px;
  object-fit: contain;
}

.brand-name {
  font-family: 'Inter', sans-serif;
  font-size: 18px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: #888;
  margin: 0 0 32px;
  font-weight: 600;
}

.hero-headline {
  font-size: clamp(32px, 5vw, 52px);
  font-weight: 800;
  line-height: 1.15;
  color: #fff;
  margin: 0 0 24px;
  letter-spacing: -0.03em;
}

.hero-sub {
  font-size: 17px;
  line-height: 1.7;
  color: #999;
  margin: 0 0 40px;
  max-width: 600px;
  margin-left: auto;
  margin-right: auto;
}

.hero-ctas {
  display: flex;
  gap: 16px;
  justify-content: center;
  flex-wrap: wrap;
}

/* ── Buttons ─────────────────────────────── */

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 14px 32px;
  border-radius: 6px;
  font-size: 15px;
  font-weight: 600;
  text-decoration: none;
  transition: all 0.2s ease;
  cursor: pointer;
  letter-spacing: 0.01em;
}

.btn-primary {
  background: #00c853;
  color: #000;
}

.btn-primary:hover {
  background: #00e676;
  transform: translateY(-1px);
}

.btn-outline {
  background: transparent;
  color: #ccc;
  border: 1px solid #333;
}

.btn-outline:hover {
  border-color: #555;
  color: #fff;
}

/* ── Section shared ──────────────────────── */

.section-heading {
  font-size: 28px;
  font-weight: 600;
  color: #fff;
  margin: 0 0 48px;
  text-align: center;
  letter-spacing: -0.02em;
}

.section-link {
  display: block;
  text-align: center;
  margin-top: 40px;
  color: #00c853;
  text-decoration: none;
  font-size: 15px;
  font-weight: 500;
  transition: color 0.2s;
}

.section-link:hover {
  color: #00e676;
}

/* ── How It Works ────────────────────────── */

.how-it-works {
  padding: 96px 24px;
  background: #0e0e0e;
}

.steps-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 32px;
  max-width: 1000px;
  margin: 0 auto;
}

.step-card {
  padding: 36px 28px;
  border: 1px solid #1a1a1a;
  border-radius: 8px;
  background: #111;
  transition: border-color 0.2s;
}

.step-card:hover {
  border-color: #00c853;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 32px;
  font-weight: 700;
  color: #00c853;
  opacity: 0.5;
  display: block;
  margin-bottom: 16px;
}

.step-title {
  font-size: 18px;
  font-weight: 600;
  color: #fff;
  margin: 0 0 10px;
}

.step-desc {
  font-size: 14px;
  line-height: 1.7;
  color: #888;
  margin: 0;
}

/* ── Feed Preview ────────────────────────── */

.feed-preview {
  padding: 96px 24px;
  background: #0a0a0a;
}

.feed-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
  max-width: 1000px;
  margin: 0 auto;
}

.feed-card {
  padding: 28px 24px;
  border: 1px solid #1a1a1a;
  border-radius: 8px;
  background: #111;
  transition: border-color 0.2s;
}

.feed-card:hover {
  border-color: #333;
}

.demo-card {
  border: 1px solid #1a1a1a;
  text-align: left;
  font: inherit;
  cursor: pointer;
  width: 100%;
}

.demo-card:hover {
  border-color: #00c853;
}

.demo-error {
  color: #ff6b6b;
  background: rgba(255, 107, 107, 0.08);
  border: 1px solid #ff6b6b;
  border-radius: 6px;
  padding: 12px 16px;
  text-align: center;
  font-size: 14px;
  max-width: 600px;
  margin: 0 auto 32px;
}

.feed-tag {
  display: inline-block;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #00c853;
  background: rgba(0, 200, 83, 0.08);
  padding: 3px 8px;
  border-radius: 3px;
  margin-bottom: 14px;
}

.feed-title {
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  margin: 0 0 10px;
  line-height: 1.4;
}

.feed-excerpt {
  font-size: 13px;
  line-height: 1.65;
  color: #777;
  margin: 0 0 16px;
}

.feed-date {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #555;
}

/* ── Pricing Preview ─────────────────────── */

.pricing-preview {
  padding: 96px 24px;
  background: #0e0e0e;
}

.pricing-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
  max-width: 840px;
  margin: 0 auto;
}

.pricing-card {
  padding: 36px 28px;
  border: 1px solid #1a1a1a;
  border-radius: 8px;
  background: #111;
  text-align: center;
  transition: border-color 0.2s;
}

.pricing-card.featured {
  border-color: #00c853;
}

.plan-name {
  font-size: 15px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #888;
  margin: 0 0 12px;
}

.plan-price {
  font-family: 'JetBrains Mono', monospace;
  font-size: 32px;
  font-weight: 700;
  color: #fff;
  margin: 0 0 8px;
}

.plan-desc {
  font-size: 13px;
  color: #666;
  margin: 0;
}

/* ── Footer ──────────────────────────────── */

.landing-footer {
  padding: 64px 24px 40px;
  border-top: 1px solid #151515;
  background: #0a0a0a;
}

.footer-inner {
  max-width: 720px;
  margin: 0 auto;
  text-align: center;
}

.footer-brand {
  font-family: 'Inter', sans-serif;
  font-size: 14px;
  letter-spacing: 0.2em;
  color: #555;
  margin: 0 0 24px;
  font-weight: 600;
}

.footer-links {
  display: flex;
  gap: 28px;
  justify-content: center;
  margin-bottom: 32px;
}

.footer-links a {
  color: #777;
  text-decoration: none;
  font-size: 14px;
  transition: color 0.2s;
}

.footer-links a:hover {
  color: #fff;
}

.footer-disclaimer {
  font-size: 12px;
  color: #444;
  line-height: 1.6;
  margin: 0 0 16px;
  max-width: 480px;
  margin-left: auto;
  margin-right: auto;
}

.footer-copy {
  font-size: 12px;
  color: #333;
  margin: 0;
}

/* ── Responsive ──────────────────────────── */

@media (max-width: 768px) {
  .steps-grid,
  .feed-grid,
  .pricing-grid {
    grid-template-columns: 1fr;
  }

  .hero {
    padding: 72px 20px 56px;
  }

  .hero-ctas {
    flex-direction: column;
    align-items: center;
  }
}
</style>
