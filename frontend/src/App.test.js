import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: { template: '<div>Home</div>' } },
  ],
})

describe('App', () => {
  it('mounts without errors', async () => {
    router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: { plugins: [router] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders router-view', async () => {
    router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: { plugins: [router] },
    })
    expect(wrapper.html()).toContain('Home')
  })

  it('renders the routed page inside exactly one <main> landmark', async () => {
    router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: { plugins: [router] },
    })
    expect(wrapper.findAll('main')).toHaveLength(1)
    expect(wrapper.find('main').text()).toContain('Home')
  })

  it('has no view or component that renders a second <main>', () => {
    const sources = import.meta.glob(['./views/*.vue', './components/**/*.vue'], {
      query: '?raw', import: 'default', eager: true,
    })
    expect(Object.keys(sources).length).toBeGreaterThan(20)
    const offenders = Object.keys(sources).filter((f) => /<main[\s>]/.test(sources[f]))
    expect(offenders).toEqual([])
  })
})
