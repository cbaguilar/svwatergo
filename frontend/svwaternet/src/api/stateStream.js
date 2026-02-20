const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

function toWsUrl(path) {
  if (API_BASE_URL) {
    const base = new URL(API_BASE_URL, window.location.origin)
    const wsProtocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${wsProtocol}//${base.host}${path}`
  }
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProtocol}//${window.location.host}${path}`
}

export function subscribeLatestState(site, { onMessage, onError, onOpen, soft = true } = {}) {
  const safeSite = encodeURIComponent(site)
  const query = soft ? '?soft=include' : ''
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
