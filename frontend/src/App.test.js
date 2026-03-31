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
})
