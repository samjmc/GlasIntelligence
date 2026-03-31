<template>
  <div class="insights">
    <header class="insights-header">
      <h1 class="insights-title">Insights</h1>
      <p class="insights-sub">Published scenario analyses and industry intelligence</p>
    </header>

    <div class="insights-body">
      <div v-if="loading" class="loading-state">Loading…</div>

      <div v-else-if="articles.length === 0" class="empty-state">
        <p>New insights published weekly. Subscribe to get notified.</p>
      </div>

      <div v-else class="articles-list">
        <article v-for="article in articles" :key="article.id" class="article-card">
          <div class="article-meta">
            <span class="article-tag">{{ article.industry || 'General' }}</span>
            <span class="article-date">{{ formatDate(article.created_at) }}</span>
          </div>
          <h2 class="article-title">{{ article.title }}</h2>
          <p class="article-excerpt">{{ truncate(article.summary, 320) }}</p>
          <router-link :to="`/feed/report/${article.id}`" class="read-link">Read Full Analysis →</router-link>
        </article>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '../composables/useApi'

const { apiGet } = useApi()
const articles = ref([])
const loading = ref(true)

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-GB', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function truncate(text, max) {
  if (!text) return ''
  if (text.length <= max) return text
  return text.slice(0, max).replace(/\s+\S*$/, '') + '…'
}

onMounted(async () => {
  try {
    const res = await apiGet('/feed/simulations')
    if (res.success && Array.isArray(res.data)) {
      articles.value = res.data
    }
  } catch {
    // feed may not be populated yet
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.insights {
  min-height: 100vh;
  background: #0a0a0a;
  color: #e0e0e0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.insights-header {
  text-align: center;
  padding: 80px 24px 48px;
  border-bottom: 1px solid #151515;
}

.insights-title {
  font-size: 36px;
  font-weight: 700;
  color: #fff;
  margin: 0 0 12px;
  letter-spacing: -0.02em;
}

.insights-sub {
  font-size: 15px;
  color: #666;
  margin: 0;
}

.insights-body {
  max-width: 760px;
  margin: 0 auto;
  padding: 48px 24px 96px;
}

.loading-state,
.empty-state {
  text-align: center;
  padding: 64px 0;
  color: #555;
  font-size: 15px;
}

.articles-list {
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.article-card {
  padding: 32px 28px;
  border: 1px solid #1a1a1a;
  border-radius: 8px;
  background: #111;
  transition: border-color 0.2s;
}

.article-card:hover {
  border-color: #282828;
}

.article-meta {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 14px;
}

.article-tag {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #00c853;
  background: rgba(0, 200, 83, 0.08);
  padding: 3px 8px;
  border-radius: 3px;
}

.article-date {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #555;
}

.article-title {
  font-size: 20px;
  font-weight: 600;
  color: #fff;
  margin: 0 0 12px;
  line-height: 1.35;
  letter-spacing: -0.02em;
}

.article-excerpt {
  font-size: 14px;
  line-height: 1.7;
  color: #777;
  margin: 0 0 18px;
}

.read-link {
  font-size: 14px;
  font-weight: 500;
  color: #00c853;
  text-decoration: none;
  transition: color 0.2s;
}

.read-link:hover {
  color: #00e676;
}

@media (max-width: 640px) {
  .insights-header {
    padding: 56px 20px 32px;
  }

  .article-card {
    padding: 24px 20px;
  }
}
</style>
