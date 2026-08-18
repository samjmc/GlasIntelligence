import { createRouter, createWebHistory } from 'vue-router'
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

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: LoginView,
    meta: { public: true },
  },
  {
    path: '/signup',
    name: 'Signup',
    component: SignupView,
    meta: { public: true },
  },
  {
    path: '/pricing',
    name: 'Pricing',
    component: PricingView,
    meta: { public: true },
  },
  {
    path: '/feed',
    name: 'Feed',
    component: FeedView,
    meta: { public: true },
  },
  {
    path: '/feed/report/:id',
    name: 'FeedReport',
    component: FeedReportView,
    props: true,
    meta: { public: true },
  },
  {
    path: '/',
    name: 'Landing',
    component: LandingView,
    meta: { public: true },
  },
  {
    path: '/insights',
    name: 'Insights',
    component: InsightsView,
    meta: { public: true },
  },
  {
    path: '/terms',
    name: 'Terms',
    component: TermsView,
    meta: { public: true },
  },
  {
    path: '/privacy',
    name: 'Privacy',
    component: PrivacyView,
    meta: { public: true },
  },
  {
    path: '/health',
    name: 'Health',
    component: { template: '<div>OK</div>' },
    meta: { public: true },
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: DashboardView,
    meta: { requiresAuth: true },
  },
  {
    path: '/compare',
    name: 'Compare',
    component: CompareView,
    meta: { requiresAuth: true },
  },
  {
    path: '/home',
    name: 'Home',
    component: Home,
  },
  {
    path: '/process/:projectId',
    name: 'Process',
    component: Process,
    props: true,
  },
  {
    path: '/simulation/:simulationId',
    name: 'Simulation',
    component: SimulationView,
    props: true,
  },
  {
    path: '/simulation/:simulationId/start',
    name: 'SimulationRun',
    component: SimulationRunView,
    props: true,
  },
  {
    path: '/report/:reportId',
    name: 'Report',
    component: ReportView,
    props: true,
  },
  {
    path: '/interaction/:reportId',
    name: 'Interaction',
    component: InteractionView,
    props: true,
  },
  {
    path: '/bundle/:bundleId',
    name: 'BundleResults',
    component: () => import('../views/BundleResultsView.vue'),
    props: true,
    meta: { requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.meta.public) return true

  if (!authState.user) {
    if (to.path === '/') {
      return { name: 'Landing' }
    }
    return { name: 'Login', query: { redirect: to.fullPath } }
  }

  return true
})

export default router
