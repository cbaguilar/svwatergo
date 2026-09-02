const STORAGE_KEY = 'svwaternet_api_backend'
const ROUTING_HEADER_STORAGE_KEY = 'svwaternet_api_routing_header'

export const BACKEND_OPTIONS = [
  { value: 'local', label: 'Localhost', baseUrl: 'http://localhost:8080' },
  { value: 'tailscale', label: 'Tailscale', baseUrl: 'http://100.112.32.80:8080' },
  { value: 'remote', label: 'svwaternet.org', baseUrl: 'https://svwaternet.org' },
]

export const ROUTING_HEADER_OPTIONS = [
  { value: 'off', label: 'Real (default)' },
  { value: 'dev', label: 'Force dev header' },
]

function browserStorage() {
  if (typeof window === 'undefined') return null
  return window.localStorage
}

function hashBackendKey() {
  if (typeof window === 'undefined') return ''
  const hash = window.location.hash || ''
  const queryIndex = hash.indexOf('?')
  if (queryIndex < 0) return ''
  const params = new URLSearchParams(hash.slice(queryIndex + 1))
  return params.get('apiBackend') || ''
}

export function getBackendKey() {
  const hashKey = hashBackendKey()
  if (BACKEND_OPTIONS.some((opt) => opt.value === hashKey)) return hashKey
  const storage = browserStorage()
  if (!storage) return 'remote'
  const key = storage.getItem(STORAGE_KEY)
  if (!key) return 'remote'
  return BACKEND_OPTIONS.some((opt) => opt.value === key) ? key : 'remote'
}

export function setBackendKey(value) {
  const storage = browserStorage()
  if (!storage) return
  storage.setItem(STORAGE_KEY, value)
}

export function getBackendRoutingHeaderKey() {
  const storage = browserStorage()
  if (!storage) return 'off'
  const key = storage.getItem(ROUTING_HEADER_STORAGE_KEY)
  if (!key) return 'off'
  return ROUTING_HEADER_OPTIONS.some((opt) => opt.value === key) ? key : 'off'
}

export function setBackendRoutingHeaderKey(value) {
  const storage = browserStorage()
  if (!storage) return
  storage.setItem(ROUTING_HEADER_STORAGE_KEY, value)
}

export function getRoutingHeaderValue() {
  const key = getBackendRoutingHeaderKey()
  if (key === 'dev') return 'dev'
  return ''
}

export function getApiBaseUrl() {
  const selected = BACKEND_OPTIONS.find((opt) => opt.value === getBackendKey())
  if (selected) return selected.baseUrl
  return import.meta.env.VITE_API_BASE_URL || ''
}
