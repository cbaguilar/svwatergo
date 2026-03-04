import { apiDelete, apiGet, apiPost, apiPut } from './client'

export function listUsers(options = {}) {
  return apiGet('/api/v1/users', options)
}

export function createUser(payload, options = {}) {
  return apiPost('/api/v1/users', payload, options)
}

export function updateUser(id, payload, options = {}) {
  return apiPut(`/api/v1/users/${id}`, payload, options)
}

export function deleteUser(id, options = {}) {
  return apiDelete(`/api/v1/users/${id}`, options)
}
