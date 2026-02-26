import React, { Suspense, useEffect, useState } from 'react'
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import { useSelector } from 'react-redux'

import { CSpinner, useColorModes } from '@coreui/react'
import './scss/style.scss'
import { clearAuthSession, getAuthToken, getStoredUser, setAuthSession } from './auth/session'
import { getAuthConfig, getMe } from './api/auth'

// We use those styles to show code examples, you should remove them in your application.
import './scss/examples.scss'

// Containers
const DefaultLayout = React.lazy(() => import('./layout/DefaultLayout'))

// Pages
const Login = React.lazy(() => import('./views/pages/login/Login'))
const Register = React.lazy(() => import('./views/pages/register/Register'))
const Page404 = React.lazy(() => import('./views/pages/page404/Page404'))
const Page500 = React.lazy(() => import('./views/pages/page500/Page500'))

const LoadingScreen = () => (
  <div className="pt-3 text-center">
    <CSpinner color="primary" variant="grow" />
  </div>
)

const App = () => {
  const { isColorModeSet, setColorMode } = useColorModes('coreui-free-react-admin-template-theme')
  const storedTheme = useSelector((state) => state.theme)
  const [authState, setAuthState] = useState({
    loading: true,
    config: null,
    authenticated: false,
    user: getStoredUser(),
    error: '',
  })

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.href.split('?')[1])
    const theme = urlParams.get('theme') && urlParams.get('theme').match(/^[A-Za-z0-9\s]+/)[0]
    if (theme) {
      setColorMode(theme)
      return
    }

    setColorMode(storedTheme || 'auto')
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let active = true
    ;(async () => {
      try {
        const config = await getAuthConfig()
        if (!active) return

        if (!config?.enabled) {
          setAuthState({
            loading: false,
            config,
            authenticated: true,
            user: null,
            error: '',
          })
          return
        }

        const token = getAuthToken()
        if (!token) {
          setAuthState({
            loading: false,
            config,
            authenticated: false,
            user: getStoredUser(),
            error: '',
          })
          return
        }

        const me = await getMe()
        if (!active) return
        setAuthSession(token, me?.user || null)
        setAuthState({
          loading: false,
          config,
          authenticated: true,
          user: me?.user || null,
          error: '',
        })
      } catch (err) {
        if (!active) return
        clearAuthSession()
        setAuthState((prev) => ({
          ...prev,
          loading: false,
          authenticated: false,
          user: null,
          error: err?.message || 'Authentication check failed',
        }))
      }
    })()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    const onAuthExpired = () => {
      clearAuthSession()
      setAuthState((prev) => ({
        ...prev,
        authenticated: false,
        user: null,
        error: 'Session expired. Please sign in again.',
      }))

      if (typeof window !== 'undefined' && window.location.hash !== '#/login') {
        window.location.hash = '#/login'
      }
    }

    window.addEventListener('svwaternet:auth-expired', onAuthExpired)
    return () => window.removeEventListener('svwaternet:auth-expired', onAuthExpired)
  }, [])

  const handleLoginSuccess = ({ token, user }) => {
    setAuthSession(token, user || null)
    setAuthState((prev) => ({
      ...prev,
      authenticated: true,
      user: user || null,
      error: '',
    }))
  }

  const handleLogout = () => {
    clearAuthSession()
    setAuthState((prev) => ({
      ...prev,
      authenticated: false,
      user: null,
      error: '',
    }))
  }

  if (authState.loading) {
    return <LoadingScreen />
  }

  return (
    <HashRouter>
      <Suspense fallback={<LoadingScreen />}>
        <Routes>
          <Route
            exact
            path="/login"
            name="Login Page"
            element={
              authState.config?.enabled && authState.authenticated ? (
                <Navigate to="/" replace />
              ) : (
                <Login
                  authConfig={authState.config}
                  authError={authState.error}
                  onLoginSuccess={handleLoginSuccess}
                />
              )
            }
          />
          <Route exact path="/register" name="Register Page" element={<Register />} />
          <Route exact path="/404" name="Page 404" element={<Page404 />} />
          <Route exact path="/500" name="Page 500" element={<Page500 />} />
          <Route
            path="*"
            name="Home"
            element={
              authState.config?.enabled && !authState.authenticated ? (
                <Navigate to="/login" replace />
              ) : (
                <DefaultLayout currentUser={authState.user} onLogout={handleLogout} />
              )
            }
          />
        </Routes>
      </Suspense>
    </HashRouter>
  )
}

export default App
