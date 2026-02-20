const DEFAULT_HEADERS = {
  Accept: 'application/json',
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

async function handleJsonResponse(response) {
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
  throw err
}

export async function apiGet(path, options = {}) {
  const url = `${API_BASE_URL}${path}`
  const headers = {
    ...DEFAULT_HEADERS,
    ...(options.headers || {}),
  }
  const response = await fetch(url, {
    method: 'GET',
    headers,
    signal: options.signal,
  })
  return handleJsonResponse(response)
}

export async function apiPost(path, body, options = {}) {
  const url = `${API_BASE_URL}${path}`
  const headers = {
    ...DEFAULT_HEADERS,
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  }
  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal: options.signal,
  })
  return handleJsonResponse(response)
}
