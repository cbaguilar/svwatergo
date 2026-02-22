const TOKEN_KEY = 'svwaternet_jwt'
const USER_KEY = 'svwaternet_user'

function storage() {
  if (typeof window === 'undefined') return null
  return window.localStorage
}

export function getAuthToken() {
  return storage()?.getItem(TOKEN_KEY) || ''
}

export function setAuthSession(token, user) {
  const s = storage()
  if (!s) return
  s.setItem(TOKEN_KEY, token || '')
  if (user) {
    s.setItem(USER_KEY, JSON.stringify(user))
  } else {
    s.removeItem(USER_KEY)
  }
}

export function clearAuthSession() {
  const s = storage()
  if (!s) return
  s.removeItem(TOKEN_KEY)
  s.removeItem(USER_KEY)
}

export function getStoredUser() {
  const raw = storage()?.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}
