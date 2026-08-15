import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', '')
  const isDemo = env.VITE_DEMO_MODE === '1'

  // Demo builds must be keyless and zero-external-origins: the static bundle
  // must never contain the Supabase URL/anon key (they'd leak credentials and
  // make initAuth() attempt real auth, redirecting guests off the demo flow).
  // envPrefix controls which vars reach import.meta.env in the client bundle —
  // in demo mode expose ONLY VITE_DEMO_* vars, so VITE_SUPABASE_URL and
  // VITE_SUPABASE_ANON_KEY from the repo-root .env cannot leak in even if set.
  return {
    envDir: '..',
    envPrefix: isDemo ? ['VITE_DEMO_'] : ['VITE_'],
    plugins: [vue()],
    server: {
      port: 3000,
      open: true,
      proxy: {
        '/api': {
          target: 'http://localhost:5001',
          changeOrigin: true,
          secure: false
        }
      }
    }
  }
})
