<template>
  <div class="pricing-page">
    <AppNavbar />
    <header class="pricing-header">
      <h1 class="pricing-title">Choose Your Plan</h1>
      <p class="pricing-subtitle">
        Multi-Agent Scenario Intelligence — powered by AI simulations
      </p>
    </header>

    <div v-if="errorMsg" class="pricing-error">{{ errorMsg }}</div>

    <section class="plans-grid">
      <!-- Free -->
      <div class="plan-card">
        <div class="plan-badge free-badge">Free</div>
        <div class="plan-price">
          <span class="price-amount">$0</span>
          <span class="price-period">forever</span>
        </div>
        <ul class="plan-features">
          <li><span class="check">&#10003;</span> 1 simulation / month</li>
          <li><span class="check">&#10003;</span> Pre-built scenarios only</li>
          <li><span class="check">&#10003;</span> Browse industry insights</li>
          <li class="feature-excluded"><span class="cross">&#10005;</span> Custom inputs</li>
          <li class="feature-excluded"><span class="cross">&#10005;</span> PDF / report exports</li>
          <li class="feature-excluded"><span class="cross">&#10005;</span> Deep Research</li>
          <li class="feature-excluded"><span class="cross">&#10005;</span> Decision Recommendations</li>
        </ul>
        <button class="plan-cta cta-secondary" @click="handleFree">
          Get Started Free
        </button>
      </div>

      <!-- Pay-as-you-go -->
      <div class="plan-card">
        <div class="plan-badge payg-badge">Pay-as-you-go</div>
        <div class="plan-price">
          <span class="price-amount">$39</span>
          <span class="price-period">/ simulation</span>
        </div>
        <ul class="plan-features">
          <li><span class="check">&#10003;</span> Full custom inputs</li>
          <li><span class="check">&#10003;</span> Full simulation output</li>
          <li><span class="check">&#10003;</span> PDF report download</li>
          <li><span class="check">&#10003;</span> Deep Research Briefing</li>
          <li><span class="check">&#10003;</span> Decision Recommendations</li>
          <li class="feature-excluded"><span class="cross">&#10005;</span> No subscription required</li>
        </ul>
        <button
          class="plan-cta cta-primary"
          :disabled="loading"
          @click="redirectToCheckout('payg')"
        >
          {{ loading === 'payg' ? 'Redirecting...' : 'Buy Simulation' }}
        </button>
      </div>

      <!-- Pro (featured) -->
      <div class="plan-card featured">
        <div class="plan-badge pro-badge">Pro</div>
        <div class="plan-price">
          <span class="price-amount">$99</span>
          <span class="price-period">/month</span>
        </div>
        <ul class="plan-features">
          <li><span class="check">&#10003;</span> 10 simulations / month</li>
          <li><span class="check">&#10003;</span> Full custom inputs</li>
          <li><span class="check">&#10003;</span> All industry feeds</li>
          <li><span class="check">&#10003;</span> PDF report downloads</li>
          <li><span class="check">&#10003;</span> Deep Research Briefings</li>
          <li><span class="check">&#10003;</span> Decision Recommendations</li>
          <li><span class="check">&#10003;</span> Save &amp; compare simulations</li>
          <li class="feature-overage">Overage: $12 / extra simulation</li>
        </ul>
        <button
          class="plan-cta cta-primary"
          :disabled="loading"
          @click="redirectToCheckout('pro')"
        >
          {{ loading === 'pro' ? 'Redirecting...' : 'Subscribe' }}
        </button>
      </div>

      <!-- Business -->
      <div class="plan-card">
        <div class="plan-badge business-badge">Business</div>
        <div class="plan-price">
          <span class="price-amount">$299</span>
          <span class="price-period">/month</span>
        </div>
        <ul class="plan-features">
          <li><span class="check">&#10003;</span> 40 simulations / month</li>
          <li><span class="check">&#10003;</span> Everything in Pro</li>
          <li><span class="check">&#10003;</span> Advanced scenario stacking</li>
          <li><span class="check">&#10003;</span> Higher agent &amp; round limits</li>
          <li><span class="check">&#10003;</span> Priority support</li>
          <li><span class="check">&#10003;</span> Team-ready exports</li>
          <li class="feature-overage">Overage: $10 / extra simulation</li>
        </ul>
        <button
          class="plan-cta cta-primary"
          :disabled="loading"
          @click="redirectToCheckout('business')"
        >
          {{ loading === 'business' ? 'Redirecting...' : 'Subscribe' }}
        </button>
      </div>

      <!-- Enterprise -->
      <div class="plan-card enterprise-card">
        <div class="plan-badge enterprise-badge">Enterprise</div>
        <div class="plan-price">
          <span class="price-amount">$1,000+</span>
          <span class="price-period">/month</span>
        </div>
        <ul class="plan-features">
          <li><span class="check">&#10003;</span> 100+ simulations / month</li>
          <li><span class="check">&#10003;</span> Custom agent configurations</li>
          <li><span class="check">&#10003;</span> Industry-specific tuning</li>
          <li><span class="check">&#10003;</span> Dedicated support</li>
          <li><span class="check">&#10003;</span> Advisory &amp; insights layer</li>
          <li><span class="check">&#10003;</span> Custom integrations</li>
        </ul>
        <a class="plan-cta cta-enterprise" href="mailto:hello@glasinsight.com?subject=Enterprise%20Inquiry">
          Contact Us
        </a>
      </div>
    </section>

    <!-- Simulation packs -->
    <section class="packs-section">
      <h2 class="packs-heading">Simulation Packs</h2>
      <p class="packs-subtitle">No subscription needed — buy simulations on demand</p>

      <div class="packs-grid">
        <div
          v-for="pack in simPacks"
          :key="pack.product"
          class="pack-card"
        >
          <span class="pack-qty">{{ pack.qty }}</span>
          <span class="pack-label">{{ pack.qty === 1 ? 'simulation' : 'simulations' }}</span>
          <span class="pack-price">${{ pack.price }}</span>
          <span class="pack-unit">${{ pack.unitPrice }} each</span>
          <span v-if="pack.save" class="pack-save">Save {{ pack.save }}</span>
          <button
            class="pack-cta"
            :disabled="loading"
            @click="redirectToCheckout(pack.product)"
          >
            {{ loading === pack.product ? 'Redirecting...' : 'Buy' }}
          </button>
        </div>
      </div>
    </section>

  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi'
import { getAccessToken } from '../store/auth'
import AppNavbar from '../components/AppNavbar.vue'

const router = useRouter()
const { apiPost } = useApi()

const loading = ref(false)
const errorMsg = ref('')

const simPacks = [
  { product: 'pack_5', qty: 5, price: 59, unitPrice: '11.80', save: null },
  { product: 'pack_10', qty: 10, price: 99, unitPrice: '9.90', save: '15%' },
]

function handleFree() {
  if (getAccessToken()) {
    router.push('/')
  } else {
    router.push('/signup')
  }
}

async function redirectToCheckout(product) {
  if (!getAccessToken()) {
    router.push({ name: 'Login', query: { redirect: '/pricing' } })
    return
  }

  loading.value = product
  errorMsg.value = ''

  try {
    const res = await apiPost('/billing/checkout', { product })
    if (res.success && res.data?.url) {
      window.location.href = res.data.url
    } else {
      errorMsg.value = res.error || 'Failed to start checkout'
      loading.value = false
    }
  } catch (err) {
    errorMsg.value = 'Network error — please try again'
    loading.value = false
  }
}
</script>

<style scoped>
.pricing-page {
  min-height: 100vh;
  background: #0a0a0a;
  color: #e0e0e0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  padding-bottom: 3rem;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.pricing-page :deep(.app-nav) {
  width: 100%;
  align-self: stretch;
}

.pricing-header {
  text-align: center;
  margin-bottom: 3rem;
}

.pricing-title {
  font-size: 2.25rem;
  font-weight: 700;
  color: #fff;
  margin: 0 0 0.5rem;
  letter-spacing: -0.02em;
}

.pricing-subtitle {
  font-size: 1.05rem;
  color: #888;
  margin: 0;
}

.pricing-error {
  background: rgba(255, 60, 60, 0.12);
  border: 1px solid rgba(255, 60, 60, 0.3);
  color: #ff6b6b;
  padding: 0.75rem 1.25rem;
  border-radius: 8px;
  margin-bottom: 2rem;
  max-width: 600px;
  text-align: center;
}

.plans-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 1.25rem;
  max-width: 1200px;
  width: 100%;
  margin-bottom: 4rem;
  padding: 0 1rem;
}

.plan-card {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 12px;
  padding: 1.75rem 1.5rem;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  transition: border-color 0.2s;
}

.plan-card:hover {
  border-color: #555;
}

.plan-card.featured {
  border-color: #00c853;
  position: relative;
}

.plan-card.featured::before {
  content: 'Most Popular';
  position: absolute;
  top: -12px;
  left: 50%;
  transform: translateX(-50%);
  background: #00c853;
  color: #0a0a0a;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 3px 12px;
  border-radius: 20px;
  white-space: nowrap;
}

.enterprise-card {
  border-color: #448aff;
}

.plan-badge {
  font-size: 0.8rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 1.25rem;
  color: #aaa;
}

.payg-badge { color: #ffab00; }
.pro-badge { color: #00c853; }
.business-badge { color: #448aff; }
.enterprise-badge { color: #b388ff; }

.plan-price {
  margin-bottom: 1.5rem;
}

.price-amount {
  font-family: 'JetBrains Mono', monospace;
  font-size: 2.25rem;
  font-weight: 700;
  color: #fff;
}

.price-period {
  font-size: 0.9rem;
  color: #666;
  margin-left: 0.15rem;
}

.plan-features {
  list-style: none;
  padding: 0;
  margin: 0 0 auto;
  width: 100%;
}

.plan-features li {
  padding: 0.4rem 0;
  font-size: 0.85rem;
  color: #bbb;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.check {
  color: #00c853;
  font-weight: 700;
  font-size: 0.85rem;
}

.cross {
  color: #555;
  font-weight: 700;
  font-size: 0.85rem;
}

.feature-excluded {
  color: #555 !important;
}

.feature-overage {
  color: #888 !important;
  font-size: 0.8rem !important;
  font-style: italic;
  padding-top: 0.6rem !important;
  border-top: 1px solid #2a2a2a;
  margin-top: 0.4rem;
}

.plan-cta {
  margin-top: 1.75rem;
  width: 100%;
  padding: 0.8rem 0;
  border-radius: 8px;
  border: none;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, opacity 0.2s;
  text-align: center;
  text-decoration: none;
  display: block;
}

.plan-cta:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.cta-primary {
  background: #00c853;
  color: #0a0a0a;
}

.cta-primary:hover:not(:disabled) {
  background: #00e676;
}

.cta-secondary {
  background: transparent;
  color: #e0e0e0;
  border: 1px solid #444;
}

.cta-secondary:hover:not(:disabled) {
  border-color: #888;
  color: #fff;
}

.cta-enterprise {
  background: transparent;
  color: #b388ff;
  border: 1px solid #7c4dff;
}

.cta-enterprise:hover {
  background: rgba(179, 136, 255, 0.1);
  color: #d1c4e9;
}

/* Simulation packs section */
.packs-section {
  text-align: center;
  max-width: 600px;
  width: 100%;
  margin-bottom: 3rem;
  padding: 0 1rem;
}

.packs-heading {
  font-size: 1.5rem;
  font-weight: 700;
  color: #fff;
  margin: 0 0 0.35rem;
  letter-spacing: -0.02em;
}

.packs-subtitle {
  font-size: 0.95rem;
  color: #888;
  margin: 0 0 1.75rem;
}

.packs-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.25rem;
}

.pack-card {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 10px;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  transition: border-color 0.2s;
}

.pack-card:hover {
  border-color: #555;
}

.pack-qty {
  font-family: 'JetBrains Mono', monospace;
  font-size: 2rem;
  font-weight: 700;
  color: #fff;
}

.pack-label {
  font-size: 0.8rem;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.pack-price {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.1rem;
  color: #00c853;
  font-weight: 600;
  margin-top: 0.5rem;
}

.pack-unit {
  font-size: 0.75rem;
  color: #666;
}

.pack-save {
  font-size: 0.75rem;
  font-weight: 600;
  color: #00c853;
  background: rgba(0, 200, 83, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
  margin-top: 0.25rem;
}

.pack-cta {
  margin-top: 0.75rem;
  width: 100%;
  padding: 0.6rem 0;
  border-radius: 6px;
  border: 1px solid #444;
  background: transparent;
  color: #e0e0e0;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}

.pack-cta:hover:not(:disabled) {
  border-color: #00c853;
  color: #00c853;
}

.pack-cta:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 1100px) {
  .plans-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .plans-grid,
  .packs-grid {
    grid-template-columns: 1fr;
    max-width: 400px;
    margin-left: auto;
    margin-right: auto;
  }

  .pricing-title {
    font-size: 1.75rem;
  }
}
</style>
