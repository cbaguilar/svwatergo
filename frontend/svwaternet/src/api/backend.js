const STORAGE_KEY = 'svwaternet_api_backend'

export const BACKEND_OPTIONS = [
  { value: 'local', label: 'Localhost', baseUrl: 'http://localhost:8080' },
  { value: 'remote', label: 'svwaternet.org', baseUrl: 'http://svwaternet.org:8080' },
]

function browserStorage() {
  if (typeof window === 'undefined') return null
  return window.localStorage
}

export function getBackendKey() {
  const storage = browserStorage()
  if (!storage) return 'local'
  const key = storage.getItem(STORAGE_KEY)
  if (!key) return 'local'
  return BACKEND_OPTIONS.some((opt) => opt.value === key) ? key : 'local'
}

export function setBackendKey(value) {
  const storage = browserStorage()
  if (!storage) return
  storage.setItem(STORAGE_KEY, value)
}

export function getApiBaseUrl() {
  const selected = BACKEND_OPTIONS.find((opt) => opt.value === getBackendKey())
  if (selected) return selected.baseUrl
  return import.meta.env.VITE_API_BASE_URL || ''
}
