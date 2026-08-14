import './style.css'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { initAuth } from './store/auth'
import { initAnalytics } from './lib/analytics'

initAnalytics()

initAuth()
  .catch(err => console.error('Auth init failed:', err))
  .then(() => {
    const app = createApp(App)
    app.use(router)
    app.mount('#app')
  })
