import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // loadEnv reads .env files; process.env carries CI job variables
  // (the demo-e2e job sets VITE_DEMO_MODE via the job's env). A demo build
  // must be detected from either source.
  const fileEnv = loadEnv(mode, '..', '')
  const isDemo = (fileEnv.VITE_DEMO_MODE || process.env.VITE_DEMO_MODE) === '1'

  // Base path for the built bundle. Default '/' keeps the root build (Cloudflare
  // custom domain) byte-identical to today; a subpath build (GitHub Pages repo
  // site, e.g. /GlasIntelligence/) sets VITE_BASE. All asset URLs and the router
  // base derive from this via import.meta.env.BASE_URL.
  const base = fileEnv.VITE_BASE || process.env.VITE_BASE || '/'

  // Demo builds must be keyless and zero-external-origins: the static bundle
  // must never contain the Supabase URL/anon key (they'd leak credentials and
  // make initAuth() attempt real auth, redirecting guests off the demo flow).
  // envPrefix controls which vars reach import.meta.env in the client bundle —
  // in demo mode expose ONLY VITE_DEMO_* vars, so VITE_SUPABASE_URL and
  // VITE_SUPABASE_ANON_KEY from the repo-root .env cannot leak in even if set.
  return {
    envDir: '..',
    base,
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
