<template>
  <nav class="app-nav">
    <router-link to="/" class="nav-brand">GLAS</router-link>
    <div class="nav-right">
      <router-link to="/dashboard" class="nav-link">Dashboard</router-link>
      <router-link to="/feed" class="nav-link">Feed</router-link>
      <router-link to="/pricing" class="nav-link">Pricing</router-link>
      <button class="nav-logout" @click="handleLogout">Logout</button>
    </div>
  </nav>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { signOut } from '../store/auth'

const router = useRouter()

async function handleLogout() {
  await signOut()
  router.push({ name: 'Landing' })
}
</script>

<style scoped>
.app-nav {
  height: 56px;
  background: #000;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 32px;
  border-bottom: 1px solid #1a1a1a;
}

.nav-brand {
  font-family: 'Inter', sans-serif;
  font-weight: 600;
  letter-spacing: 0.2em;
  font-size: 14px;
  color: #fff;
  text-decoration: none;
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 24px;
}

.nav-link {
  color: #888;
  text-decoration: none;
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  font-weight: 500;
  transition: color 0.2s;
}

.nav-link:hover,
.nav-link.router-link-active {
  color: #fff;
}

.nav-logout {
  background: transparent;
  border: 1px solid #333;
  color: #888;
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  font-weight: 500;
  padding: 5px 14px;
  cursor: pointer;
  transition: all 0.2s;
  border-radius: 4px;
}

.nav-logout:hover {
  border-color: #666;
  color: #fff;
}
</style>
