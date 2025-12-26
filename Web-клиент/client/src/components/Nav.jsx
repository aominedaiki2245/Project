import React from 'react'
import { Link } from 'react-router-dom'
import { openAuthPopup } from '../auth'

export default function Nav({ user, onLogout }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
      <div>
        <Link to="/tests">Тесты</Link>
      </div>
      <div>
        {user ? (
          <>
            <span style={{ marginRight: 10 }}>{user.fullName || user.email}</span>
            <button onClick={onLogout}>Выйти</button>
          </>
        ) : (
          <>
            <button onClick={() => openAuthPopup('google')}>Login with Google</button>
            <button style={{ marginLeft: 8 }} onClick={() => openAuthPopup('github')}>Login with GitHub</button>
          </>
        )}
      </div>
    </div>
  )
}
