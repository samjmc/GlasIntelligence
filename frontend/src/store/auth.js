import { reactive } from 'vue'
import { supabase } from '../lib/supabase'

export const authState = reactive({
  user: null,
  session: null,
  loading: true,
  initialized: false,
})

export async function initAuth() {
  if (!supabase) {
    authState.user = { id: 'local', email: 'local@dev' }
    authState.loading = false
    authState.initialized = true
    return
  }

  const { data: { session } } = await supabase.auth.getSession()
  authState.session = session
  authState.user = session?.user ?? null
  authState.loading = false
  authState.initialized = true

  supabase.auth.onAuthStateChange((_event, session) => {
    authState.session = session
    authState.user = session?.user ?? null
  })
}

export async function signUp(email, password, displayName) {
  if (!supabase) throw new Error('Auth not configured')
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { data: { display_name: displayName } },
  })
  if (error) throw error
  return data
}

export async function signIn(email, password) {
  if (!supabase) throw new Error('Auth not configured')
  const { data, error } = await supabase.auth.signInWithPassword({ email, password })
  if (error) throw error
  return data
}

export async function signOut() {
  if (!supabase) return
  await supabase.auth.signOut()
  authState.user = null
  authState.session = null
}

export function getAccessToken() {
  return authState.session?.access_token || ''
}

export async function refreshAccessToken() {
  if (!supabase) return
  const { data: { session } } = await supabase.auth.getSession()
  if (session) {
    authState.session = session
    authState.user = session.user ?? null
  }
}
