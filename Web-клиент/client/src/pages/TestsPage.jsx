import React, { useEffect, useState } from 'react'
import { apiFetch } from '../apiClient'
import { Link } from 'react-router-dom'

export default function TestsPage() {
  const [tests, setTests] = useState([])

  useEffect(() => {
    async function load() {
      const r = await apiFetch('/tests', { method: 'GET' })
      if (r.ok) {
        const data = await r.json()
        setTests(data)
      } else {
        // handle errors
      }
    }
    load()
  }, [])

  return (
    <div>
      <h2>Список тестов</h2>
      <ul>
        {tests.map(t => (
          <li key={t.id}>
            <strong>{t.title}</strong> — <Link to={`/attempt/${t.id}`}>Пройти</Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
