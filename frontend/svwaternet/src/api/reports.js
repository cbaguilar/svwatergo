import { apiDelete, apiGet, apiPost, apiPut } from './client'

export function listOperatorReports(site, { status, q, limit = 20, offset = 0, signal } = {}) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (q) params.set('q', q)
  if (limit != null) params.set('limit', String(limit))
  if (offset != null) params.set('offset', String(offset))
  const qs = params.toString()
  return apiGet(`/api/v1/sites/${site}/operator-reports${qs ? `?${qs}` : ''}`, { signal })
}

export function createOperatorReport(site, body, options = {}) {
  return apiPost(`/api/v1/sites/${site}/operator-reports`, body, options)
}

export function updateOperatorReport(site, id, body, options = {}) {
  return apiPut(`/api/v1/sites/${site}/operator-reports/${id}`, body, options)
}

export function deleteOperatorReport(site, id, options = {}) {
  return apiDelete(`/api/v1/sites/${site}/operator-reports/${id}`, options)
}
