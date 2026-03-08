import { apiPostBlob } from './client'

export function generateAlertFormPdf(site, payload, options = {}) {
  return apiPostBlob(`/api/v1/sites/${encodeURIComponent(site)}/alert-forms/pdf`, payload, options)
}

