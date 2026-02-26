import { getApiBaseUrl } from './backend'
import { getAuthToken } from '../auth/session'

const DEFAULT_HEADERS = {
  Accept: 'application/json',
}

function notifyAuthExpired() {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent('svwaternet:auth-expired'))
}

async function handleJsonResponse(response, options = {}) {
  const contentType = response.headers.get('content-type') || ''
  const isJson = contentType.includes('application/json')
  const payload = isJson ? await response.json() : null

  if (response.ok) {
    return payload
  }

  const message =
    payload?.error?.message ||
    payload?.error ||
    payload?.message ||
    `Request failed with status ${response.status}`
  const err = new Error(message)
  err.status = response.status
  err.payload = payload
  if (response.status === 401 && !options.skipAuth) {
    notifyAuthExpired()
  }
  throw err
}

function buildHeaders(options = {}, isJSON = false) {
  const headers = {
    ...DEFAULT_HEADERS,
    ...(isJSON ? { 'Content-Type': 'application/json' } : {}),
    ...(options.headers || {}),
  }
  if (!options.skipAuth) {
    const token = getAuthToken()
    if (token && !headers.Authorization) {
      headers.Authorization = `Bearer ${token}`
    }
  }
  return headers
}

export async function apiGet(path, options = {}) {
  const url = `${getApiBaseUrl()}${path}`
  const headers = buildHeaders(options, false)
  const response = await fetch(url, {
    method: 'GET',
    headers,
    signal: options.signal,
  })
  return handleJsonResponse(response, options)
}

export async function apiPost(path, body, options = {}) {
  const url = `${getApiBaseUrl()}${path}`
  const headers = buildHeaders(options, true)
  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal: options.signal,
  })
  return handleJsonResponse(response, options)
}

export async function apiPut(path, body, options = {}) {
  const url = `${getApiBaseUrl()}${path}`
  const headers = buildHeaders(options, true)
  const response = await fetch(url, {
    method: 'PUT',
    headers,
    body: JSON.stringify(body),
    signal: options.signal,
  })
  return handleJsonResponse(response, options)
}

export async function apiDelete(path, options = {}) {
  const url = `${getApiBaseUrl()}${path}`
  const headers = buildHeaders(options, false)
  const response = await fetch(url, {
    method: 'DELETE',
    headers,
    signal: options.signal,
  })
  return handleJsonResponse(response, options)
}
