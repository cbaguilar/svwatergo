import { apiGet, apiPost } from './client'

export function getAuthConfig(options = {}) {
  return apiGet('/api/v1/auth/config', { ...options, skipAuth: true })
}

export function exchangeGoogleCredential(credential, options = {}) {
  return apiPost('/api/v1/auth/google/exchange', { credential }, { ...options, skipAuth: true })
}

export function getMe(options = {}) {
  return apiGet('/api/v1/auth/me', options)
}
