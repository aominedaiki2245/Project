import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import App from './App'
import LoginPage from './pages/LoginPage'
import TestsPage from './pages/TestsPage'
import AttemptPage from './pages/AttemptPage'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />}>
          <Route index element={<LoginPage />} />
          <Route path="tests" element={<TestsPage />} />
          <Route path="attempt/:id" element={<AttemptPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
)
