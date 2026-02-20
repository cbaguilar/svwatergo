import { apiGet } from './client'

export function fetchLatestState(site, options = {}) {
  const { ...requestOptions } = options
  const safeSite = encodeURIComponent(site)
  const path = `/api/v1/sites/${safeSite}/state/latest?soft=include`
  return apiGet(path, requestOptions)
}
