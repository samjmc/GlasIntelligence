<template>
  <div class="not-found-page">
    <div class="not-found-container">
      <h1>Page not found</h1>
      <p>The page you are looking for does not exist or has moved.</p>
      <router-link to="/" class="home-link">Go to home page</router-link>
    </div>
  </div>
</template>

<style scoped>
.not-found-page {
  min-height: 100vh;
  background: #0a0a0a;
  color: #e0e0e0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4rem 1.5rem;
}

.not-found-container {
  max-width: 480px;
  text-align: center;
}

h1 {
  font-size: 2rem;
  font-weight: 700;
  color: #ffffff;
  margin-bottom: 1rem;
  letter-spacing: -0.02em;
}

p {
  font-size: 0.95rem;
  line-height: 1.7;
  color: #b0b0b0;
  margin-bottom: 2rem;
}

.home-link {
  display: inline-block;
  padding: 10px 20px;
  border: 1px solid #333;
  border-radius: 4px;
  color: #ffffff;
  text-decoration: none;
  font-size: 0.9rem;
  font-weight: 500;
}

.home-link:hover {
  border-color: #666;
}
</style>
