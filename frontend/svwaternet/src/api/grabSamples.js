import { apiDelete, apiGet, apiPost, apiPut } from './client'

export function listGrabSamples(site, { q, limit = 50, offset = 0, signal } = {}) {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  if (limit != null) params.set('limit', String(limit))
  if (offset != null) params.set('offset', String(offset))
  const qs = params.toString()
  return apiGet(`/api/v1/sites/${site}/grab-samples${qs ? `?${qs}` : ''}`, { signal })
}

export function createGrabSample(site, body, options = {}) {
  return apiPost(`/api/v1/sites/${site}/grab-samples`, body, options)
}

export function updateGrabSample(site, id, body, options = {}) {
  return apiPut(`/api/v1/sites/${site}/grab-samples/${id}`, body, options)
}

export function deleteGrabSample(site, id, options = {}) {
  return apiDelete(`/api/v1/sites/${site}/grab-samples/${id}`, options)
}
