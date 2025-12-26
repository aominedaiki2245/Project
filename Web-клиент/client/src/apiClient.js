// небольшой wrapper: хранит access token в localStorage (или памяти)
// и пытается обновить через /auth/refresh при 401.
export function getAccessToken() {
  return localStorage.getItem('access_token')
}
export function setAccessToken(t) {
  if (!t) localStorage.removeItem('access_token')
  else localStorage.setItem('access_token', t)
}

export async function apiFetch(path, opts = {}) {
  const token = getAccessToken()
  opts.headers = opts.headers || {}
  opts.credentials = opts.credentials || 'include'
  if (token) opts.headers['Authorization'] = `Bearer ${token}`

  let r = await fetch(`/api${path}`, opts)
  if (r.status === 401) {
    // try refresh
    const rr = await fetch('/auth/refresh', { method: 'POST', credentials: 'include' })
    if (rr.ok) {
      const data = await rr.json()
      setAccessToken(data.access_token)
      opts.headers['Authorization'] = `Bearer ${data.access_token}`
      r = await fetch(`/api${path}`, opts)
    }
  }
  return r
}
