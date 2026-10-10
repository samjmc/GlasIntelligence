import { createRouter, createWebHistory } from 'vue-router'
import { isDemoMode } from '../demo/config'
import { authState } from '../store/auth'
import Home from '../views/Home.vue'
import Process from '../views/MainView.vue'
import SimulationView from '../views/SimulationView.vue'
import SimulationRunView from '../views/SimulationRunView.vue'
import ReportView from '../views/ReportView.vue'
import InteractionView from '../views/InteractionView.vue'
import LoginView from '../views/LoginView.vue'
import SignupView from '../views/SignupView.vue'
import PricingView from '../views/PricingView.vue'
import FeedView from '../views/FeedView.vue'
import FeedReportView from '../views/FeedReportView.vue'
import DashboardView from '../views/DashboardView.vue'
import CompareView from '../views/CompareView.vue'
import LandingView from '../views/LandingView.vue'
import InsightsView from '../views/InsightsView.vue'
import TermsView from '../views/TermsView.vue'
import PrivacyView from '../views/PrivacyView.vue'
import NotFoundView from '../views/NotFoundView.vue'

export const BASE_TITLE = 'Glas Intelligence'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: LoginView,
    meta: { public: true, guestOnly: true, title: 'Log in' },
  },
  {
    path: '/signup',
    name: 'Signup',
    component: SignupView,
    meta: { public: true, guestOnly: true, title: 'Sign up' },
  },
  {
    path: '/pricing',
    name: 'Pricing',
    component: PricingView,
    meta: { public: true, title: 'Pricing' },
  },
  {
    path: '/feed',
    name: 'Feed',
    component: FeedView,
    meta: { public: true, title: 'Intelligence Feed' },
  },
  {
    path: '/feed/report/:id',
    name: 'FeedReport',
    component: FeedReportView,
    props: true,
    meta: { public: true, title: 'Feed Report' },
  },
  {
    path: '/landing',
    name: 'Landing',
    component: LandingView,
    meta: { public: true, title: 'Scenario Intelligence' },
  },
  {
    path: '/insights',
    name: 'Insights',
    component: InsightsView,
    meta: { public: true, title: 'Insights' },
  },
  {
    path: '/terms',
    name: 'Terms',
    component: TermsView,
    meta: { public: true, title: 'Terms of Service' },
  },
  {
    path: '/privacy',
    name: 'Privacy',
    component: PrivacyView,
    meta: { public: true, title: 'Privacy Policy' },
  },
  {
    path: '/health',
    name: 'Health',
    component: { template: '<div>OK</div>' },
    meta: { public: true, title: 'Health' },
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: DashboardView,
    meta: { requiresAuth: true, title: 'Dashboard' },
  },
  {
    path: '/compare',
    name: 'Compare',
    component: CompareView,
    meta: { requiresAuth: true, title: 'Compare' },
  },
  {
    path: '/',
    name: 'Home',
    component: Home,
    meta: { title: 'New Scenario' },
  },
  {
    path: '/process/:projectId',
    name: 'Process',
    component: Process,
    props: true,
    meta: { title: 'Knowledge Graph' },
  },
  {
    path: '/simulation/:simulationId',
    name: 'Simulation',
    component: SimulationView,
    props: true,
    meta: { title: 'Environment Setup' },
  },
  {
    path: '/simulation/:simulationId/start',
    name: 'SimulationRun',
    component: SimulationRunView,
    props: true,
    meta: { title: 'Run Simulation' },
  },
  {
    path: '/report/:reportId',
    name: 'Report',
    component: ReportView,
    props: true,
    meta: { title: 'Report' },
  },
  {
    path: '/interaction/:reportId',
    name: 'Interaction',
    component: InteractionView,
    props: true,
    meta: { title: 'Deep Interaction' },
  },
  {
    path: '/bundle/:bundleId',
    name: 'BundleResults',
    component: () => import('../views/BundleResultsView.vue'),
    props: true,
    meta: { requiresAuth: true, title: 'Bundle Results' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: NotFoundView,
    meta: { public: true, title: 'Page not found' },
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// Only same-site paths: "//host" or "https://..." would send the user off the site.
function safeRedirect(redirect) {
  return typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//')
    ? redirect
    : '/dashboard'
}

router.beforeEach((to) => {
  // The demo build is keyless: no accounts, no billing, no feed. Product-only
  // routes would render forms/pages that cannot work — send them home.
  if (isDemoMode && ['/login', '/signup', '/feed', '/pricing'].includes(to.path)) {
    return { path: '/' }
  }

  // A signed-in user has no use for the login/signup forms.
  if (to.meta.guestOnly && authState.user) {
    return safeRedirect(to.query.redirect)
  }

  if (to.meta.public) return true

  if (!authState.user) {
    if (to.path === '/') {
      return { name: 'Landing' }
    }
    return { name: 'Login', query: { redirect: to.fullPath } }
  }

  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · ${BASE_TITLE}` : BASE_TITLE
})

export default router
