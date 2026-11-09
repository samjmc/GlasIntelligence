import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// A stranger must agree to the Terms and Privacy Policy before an account is made.

const signUp = vi.hoisted(() => vi.fn(async () => ({})))
vi.mock('../store/auth', () => ({ signUp }))

import SignupView from './SignupView.vue'

async function fillForm(wrapper) {
  await wrapper.find('#displayName').setValue('Jane Smith')
  await wrapper.find('#email').setValue('jane@example.com')
  await wrapper.find('#password').setValue('correct-horse')
  await wrapper.find('#confirmPassword').setValue('correct-horse')
}

describe('SignupView consent', () => {
  afterEach(() => vi.clearAllMocks())

  it('keeps Create Account disabled until the consent box is ticked', async () => {
    const wrapper = mount(SignupView, { global: { stubs: { RouterLink: true } } })
    await fillForm(wrapper)

    const btn = () => wrapper.find('[data-test="signup-submit"]')
    expect(btn().attributes('disabled')).toBeDefined()
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(signUp).not.toHaveBeenCalled()

    await wrapper.find('[data-test="consent"]').setValue(true)
    expect(btn().attributes('disabled')).toBeUndefined()
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(signUp).toHaveBeenCalledWith('jane@example.com', 'correct-horse', 'Jane Smith')
    wrapper.unmount()
  })

  it('links the consent text to /terms and /privacy and says the email can take a while', () => {
    const wrapper = mount(SignupView, { global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } })
    const consent = wrapper.find('.auth-consent')
    expect(consent.text().replace(/\s+/g, ' ')).toBe('I agree to the Terms of Service and Privacy Policy')
    expect(consent.findAll('a').map((a) => a.attributes('href'))).toEqual(['/terms', '/privacy'])
    expect(wrapper.find('.auth-hint').text()).toBe(
      'We will email you a link to confirm your address. It can take a few minutes.',
    )
    wrapper.unmount()
  })
})
