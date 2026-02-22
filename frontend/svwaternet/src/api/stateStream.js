import { getApiBaseUrl } from './backend'
import { getAuthToken } from '../auth/session'

function toWsUrl(path) {
  const apiBaseUrl = getApiBaseUrl()
  if (apiBaseUrl) {
    const base = new URL(apiBaseUrl, window.location.origin)
    const wsProtocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${wsProtocol}//${base.host}${path}`
  }
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProtocol}//${window.location.host}${path}`
}

export function subscribeLatestState(site, { onMessage, onError, onOpen, soft = true } = {}) {
  const safeSite = encodeURIComponent(site)
  const params = new URLSearchParams()
  if (soft) params.set('soft', 'include')
  const token = getAuthToken()
  if (token) params.set('access_token', token)
  const query = params.toString() ? `?${params.toString()}` : ''
  const ws = new WebSocket(toWsUrl(`/api/v1/sites/${safeSite}/state/stream${query}`))

  ws.onopen = () => {
    if (onOpen) onOpen()
  }

  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data)
      if (onMessage) onMessage(payload)
    } catch (err) {
      if (onError) onError(err)
    }
  }

  ws.onerror = (event) => {
    if (onError) onError(event)
  }

  return ws
}
