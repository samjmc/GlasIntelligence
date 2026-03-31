<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-brand">
        <span class="brand-mark">GLAS</span>
        <span class="brand-dot"></span>
      </div>

      <h1 class="auth-title">Sign in to Glas Intelligence</h1>
      <p class="auth-subtitle">Multi-Agent Scenario Intelligence Platform</p>

      <form class="auth-form" @submit.prevent="handleLogin">
        <div v-if="errorMsg" class="auth-error">
          <span class="error-icon">!</span>
          {{ errorMsg }}
        </div>

        <label class="auth-label" for="email">Email</label>
        <input
          id="email"
          v-model="email"
          type="email"
          class="auth-input"
          placeholder="you@company.com"
          autocomplete="email"
          required
        />

        <label class="auth-label" for="password">Password</label>
        <input
          id="password"
          v-model="password"
          type="password"
          class="auth-input"
          placeholder="••••••••"
          autocomplete="current-password"
          required
        />

        <button type="submit" class="auth-btn" :disabled="submitting">
          <span v-if="!submitting">Sign In</span>
          <span v-else>Signing in…</span>
          <span class="btn-arrow">→</span>
        </button>
      </form>

      <p class="auth-footer">
        Don't have an account?
        <router-link to="/signup" class="auth-link">Sign up</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { signIn } from '../store/auth'

const router = useRouter()
const route = useRoute()
const email = ref('')
const password = ref('')
const errorMsg = ref('')
const submitting = ref(false)

async function handleLogin() {
  errorMsg.value = ''
  submitting.value = true
  try {
    await signIn(email.value, password.value)
    router.push(route.query.redirect || '/')
  } catch (err) {
    errorMsg.value = err.message || 'Sign in failed'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0a0a0a;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  padding: 24px;
}

.auth-card {
  width: 100%;
  max-width: 400px;
  padding: 48px 40px;
  background: #111111;
  border: 1px solid #1e1e1e;
  border-radius: 2px;
}

.auth-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 36px;
}

.brand-mark {
  font-family: 'Inter', sans-serif;
  font-weight: 600;
  font-size: 1.3rem;
  color: #ffffff;
  letter-spacing: 0.2em;
}

.brand-dot {
  width: 8px;
  height: 8px;
  background: #22c55e;
  border-radius: 1px;
}

.auth-title {
  font-size: 1.4rem;
  font-weight: 600;
  color: #f0f0f0;
  margin: 0 0 8px 0;
  letter-spacing: -0.02em;
}

.auth-subtitle {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 0.72rem;
  color: #555;
  margin: 0 0 32px 0;
  letter-spacing: 0.5px;
}

.auth-form {
  display: flex;
  flex-direction: column;
}

.auth-label {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 0.72rem;
  color: #888;
  margin-bottom: 6px;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}

.auth-input {
  width: 100%;
  padding: 12px 14px;
  background: #0a0a0a;
  border: 1px solid #262626;
  color: #e0e0e0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 0.9rem;
  outline: none;
  border-radius: 2px;
  margin-bottom: 20px;
  transition: border-color 0.2s;
}

.auth-input::placeholder {
  color: #444;
}

.auth-input:focus {
  border-color: #22c55e;
}

.auth-btn {
  width: 100%;
  padding: 14px;
  margin-top: 8px;
  background: #22c55e;
  color: #000;
  border: none;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-weight: 700;
  font-size: 0.95rem;
  letter-spacing: 0.5px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-radius: 2px;
  transition: background 0.2s, transform 0.1s;
}

.auth-btn:hover:not(:disabled) {
  background: #16a34a;
  transform: translateY(-1px);
}

.auth-btn:active:not(:disabled) {
  transform: translateY(0);
}

.auth-btn:disabled {
  background: #1a3a22;
  color: #555;
  cursor: not-allowed;
}

.btn-arrow {
  font-size: 1.1rem;
}

.auth-error {
  background: rgba(220, 38, 38, 0.1);
  border: 1px solid rgba(220, 38, 38, 0.3);
  color: #ef4444;
  padding: 10px 14px;
  font-size: 0.82rem;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-radius: 2px;
}

.error-icon {
  width: 18px;
  height: 18px;
  border: 1px solid #ef4444;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.7rem;
  font-weight: 700;
  flex-shrink: 0;
}

.auth-footer {
  text-align: center;
  margin-top: 28px;
  font-size: 0.85rem;
  color: #555;
}

.auth-link {
  color: #22c55e;
  text-decoration: none;
  font-weight: 600;
}

.auth-link:hover {
  text-decoration: underline;
}
</style>
