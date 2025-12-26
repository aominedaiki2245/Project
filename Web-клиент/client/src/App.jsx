import React, { useState, useEffect } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import Nav from './components/Nav'
import { apiFetch, setAccessToken, getAccessToken } from './apiClient'

export default function App() {
  const [user, setUser] = useState(null)
  const navigate = useNavigate()

  // receive access_token posted by auth popup
  useEffect(() => {
    function handler(e) {
      // check origin in prod
      if (e.data && e.data.type === 'oauth' && e.data.payload) {
        const payload = e.data.payload
        if (payload.access_token) {
          setAccessToken(payload.access_token)
        }
        if (payload.user) setUser(payload.user)
        // redirect to tests
        navigate('/tests')
      }
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [])

  // try to refresh on load if no access token
  useEffect(() => {
    async function tryRefresh() {
      if (!getAccessToken()) {
        try {
          const r = await fetch('/auth/refresh', { method: 'POST', credentials: 'include' })
          if (r.ok) {
            const data = await r.json()
            setAccessToken(data.access_token)
            if (data.user) setUser(data.user)
            navigate('/tests')
          }
        } catch (e) {}
      }
    }
    tryRefresh()
  }, [])

  return (
    <div style={{ padding: 20, fontFamily: 'Arial, sans-serif' }}>
      <Nav user={user} onLogout={async () => {
        await fetch('/auth/logout', { method: 'POST', credentials: 'include' })
        localStorage.removeItem('access_token')
        setUser(null)
        navigate('/')
      }} />
      <Outlet />
    </div>
  )
}
