import { getAccessToken } from '../store/auth'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export function useApi() {
  function authHeaders() {
    const token = getAccessToken()
    const headers = { 'Content-Type': 'application/json' }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    return headers
  }

  async function handleResponse(res) {
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      const err = new Error(body.error || `Request failed (${res.status})`)
      err.status = res.status
      err.body = body
      throw err
    }
    return res.json()
  }

  async function apiGet(path) {
    const res = await fetch(`${API_BASE}${path}`, { headers: authHeaders() })
    return handleResponse(res)
  }

  async function apiPost(path, body) {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(body),
    })
    return handleResponse(res)
  }

  async function apiDelete(path) {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
    return handleResponse(res)
  }

  async function apiUpload(path, formData) {
    const token = getAccessToken()
    const headers = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers,
      body: formData,
    })
    return handleResponse(res)
  }

  return { apiGet, apiPost, apiDelete, apiUpload, authHeaders }
}
