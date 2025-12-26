import React from 'react'
import { openAuthPopup } from '../auth'

export default function LoginPage() {
  return (
    <div>
      <h2>Войти</h2>
      <p>Войдите через внешний провайдер</p>
      <button onClick={() => openAuthPopup('google')}>Google</button>
      <button style={{ marginLeft: 8 }} onClick={() => openAuthPopup('github')}>GitHub</button>
    </div>
  )
}
