import { apiGet } from './client'

export function fetchLatestState(site, options = {}) {
  const { soft = true, ...requestOptions } = options
  const safeSite = encodeURIComponent(site)
  const query = soft ? '?soft=include' : ''
  const path = `/api/v1/sites/${safeSite}/state/latest${query}`
  return apiGet(path, requestOptions)
}

export function fetchStateRange(site, { start, end, soft = true, signal } = {}) {
  const safeSite = encodeURIComponent(site)
  const params = new URLSearchParams()
  if (start) params.set('start', start)
  if (end) params.set('end', end)
  if (soft) params.set('soft', 'include')
  params.set('sample', 'stride')
  params.set('max_points', '1000')
  const path = `/api/v1/sites/${safeSite}/state?${params.toString()}`
  return apiGet(path, { signal })
}

export function fetchDailySummary(site, { signal } = {}) {
  const safeSite = encodeURIComponent(site)
  return apiGet(`/api/v1/sites/${safeSite}/summary/daily`, { signal })
}

export function fetchNextStateForecast(site, { signal } = {}) {
  const safeSite = encodeURIComponent(site)
  return apiGet(`/api/v1/sites/${safeSite}/forecast/next-state`, { signal })
}
