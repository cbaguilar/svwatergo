import { apiGet, apiPost, apiPostMultipart } from './client'
import { getApiBaseUrl } from './backend'

export function fetchAudioSources({ site = '', signal } = {}) {
  const params = new URLSearchParams()
  if (site) params.set('site', site)
  const query = params.toString()
  return apiGet(`/api/v1/audio/sources${query ? `?${query}` : ''}`, { signal })
}

export function fetchAudioArtifacts({
  site = '',
  sourceKey = '',
  start = '',
  end = '',
  format = '',
  limit = 50,
  signal,
} = {}) {
  const params = new URLSearchParams()
  if (site) params.set('site', site)
  if (sourceKey) params.set('source_key', sourceKey)
  if (start) params.set('start', start)
  if (end) params.set('end', end)
  if (format) params.set('format', format)
  if (limit) params.set('limit', String(limit))
  const query = params.toString()
  return apiGet(`/api/v1/audio/artifacts${query ? `?${query}` : ''}`, { signal })
}

export function stageAudioFile(file, { signal } = {}) {
  const form = new FormData()
  form.append('file', file)
  return apiPostMultipart('/api/v1/analytics/audio-inference-stage', form, { signal })
}

export function createAudioInferenceRun(payload, { signal } = {}) {
  return apiPost('/api/v1/analytics/audio-inference-runs', payload, { signal })
}

export function fetchAnalyticsJob(id, { signal } = {}) {
  return apiGet(`/api/v1/analytics/jobs/${encodeURIComponent(id)}`, { signal })
}

export function audioArtifactPlaybackUrl(id) {
  if (!id) return ''
  return `${getApiBaseUrl()}/api/v1/audio/artifacts/${encodeURIComponent(id)}/play`
}

export function localAudioPlaybackUrl(path) {
  if (!path?.trim()) return ''
  const params = new URLSearchParams({ path: path.trim() })
  return `${getApiBaseUrl()}/api/v1/audio/local-file?${params.toString()}`
}

export function localAudioSpectrogramUrl(path) {
  if (!path?.trim()) return ''
  const params = new URLSearchParams({ path: path.trim() })
  return `${getApiBaseUrl()}/api/v1/audio/local-file/spectrogram?${params.toString()}`
}
