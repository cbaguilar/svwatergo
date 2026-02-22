import React, { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CAlert,
  CButton,
  CCard,
  CCardBody,
  CCardGroup,
  CCol,
  CContainer,
  CSpinner,
  CRow,
} from '@coreui/react'
import { exchangeGoogleCredential } from '../../../api/auth'

const GOOGLE_SCRIPT_ID = 'google-identity-services'

function loadGoogleScript() {
  return new Promise((resolve, reject) => {
    if (typeof window === 'undefined') {
      reject(new Error('Browser environment required'))
      return
    }
    if (window.google?.accounts?.id) {
      resolve()
      return
    }
    const existing = document.getElementById(GOOGLE_SCRIPT_ID)
    if (existing) {
      existing.addEventListener('load', () => resolve(), { once: true })
      existing.addEventListener('error', () => reject(new Error('Failed to load Google SDK')), {
        once: true,
      })
      return
    }
    const script = document.createElement('script')
    script.id = GOOGLE_SCRIPT_ID
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load Google SDK'))
    document.head.appendChild(script)
  })
}

const Login = ({ authConfig, authError, onLoginSuccess }) => {
  const googleBtnRef = useRef(null)
  const [localError, setLocalError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    const googleClientId = authConfig?.googleClientId
    if (!authConfig?.enabled || !googleClientId || !authConfig?.sessionJwt || !googleBtnRef.current) {
      return undefined
    }

    loadGoogleScript()
      .then(() => {
        if (!active || !window.google?.accounts?.id) return
        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: async (response) => {
            if (!active) return
            setBusy(true)
            setLocalError('')
            try {
              const result = await exchangeGoogleCredential(response.credential)
              onLoginSuccess?.({ token: result.token, user: result.user })
            } catch (err) {
              setLocalError(err?.message || 'Google login failed')
            } finally {
              setBusy(false)
            }
          },
        })

        googleBtnRef.current.innerHTML = ''
        window.google.accounts.id.renderButton(googleBtnRef.current, {
          theme: 'outline',
          size: 'large',
          type: 'standard',
          text: 'signin_with',
          shape: 'pill',
          width: 320,
        })
      })
      .catch((err) => {
        if (active) {
          setLocalError(err?.message || 'Failed to load Google login')
        }
      })

    return () => {
      active = false
    }
  }, [authConfig, onLoginSuccess])

  const configError =
    authConfig?.enabled && !authConfig?.sessionJwt
      ? 'Server auth is enabled, but JWT sessions are not configured (set JWT_SECRET).'
      : ''

  const showGoogle = authConfig?.enabled && authConfig?.googleClientId && authConfig?.sessionJwt
  const normalizeAccessError = (value) => {
    const msg = String(value || '').trim().toLowerCase()
    if (!msg) return value
    if (msg.includes('forbidden') || msg.includes('unauthorized') || msg.includes('403')) {
      return 'Unauthorized, please reach out to the UCLA WaTeR group for access.'
    }
    return value
  }
  const normalizedAuthError = normalizeAccessError(authError)
  const normalizedLocalError = normalizeAccessError(localError)

  return (
    <div className="bg-body-tertiary min-vh-100 d-flex flex-row align-items-center">
      <CContainer>
        <CRow className="justify-content-center">
          <CCol md={8}>
            <CCardGroup>
              <CCard className="p-4">
                <CCardBody>
                  <h1>Login</h1>
                  <p className="text-body-secondary">Sign in with your Google account</p>
                  {normalizedAuthError ? <CAlert color="danger">{normalizedAuthError}</CAlert> : null}
                  {configError ? <CAlert color="warning">{configError}</CAlert> : null}
                  {normalizedLocalError ? <CAlert color="danger">{normalizedLocalError}</CAlert> : null}
                  {!authConfig?.enabled ? (
                    <CAlert color="info">Authentication is disabled on this backend.</CAlert>
                  ) : null}
                  {showGoogle ? (
                    <div className="d-flex flex-column gap-3">
                      <div ref={googleBtnRef} />
                      {busy ? (
                        <div className="text-body-secondary d-flex align-items-center gap-2">
                          <CSpinner size="sm" />
                          Signing in...
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </CCardBody>
              </CCard>
              <CCard className="text-white bg-primary py-5" style={{ width: '44%' }}>
                <CCardBody className="text-center">
                  <div>
                    <h2>SVWATERNET</h2>
                    <p>
                      Live monitoring and analysis of remote drinking water systems in the Salinas
                      Valley of Central California.
                    </p>
                    <p className="mb-0">
                      A project of the WaTeR group at UCLA. Learn more at{' '}
                      <a
                        href="https://cleanwater.seas.ucla.edu/"
                        target="_blank"
                        rel="noreferrer"
                        className="text-white"
                      >
                        cleanwater.seas.ucla.edu
                      </a>
                    </p>
                    <Link to="/">
                      <CButton color="light" className="mt-3" variant="outline" tabIndex={-1}>
                        Back to Dashboard
                      </CButton>
                    </Link>
                  </div>
                </CCardBody>
              </CCard>
            </CCardGroup>
          </CCol>
        </CRow>
      </CContainer>
    </div>
  )
}

export default Login
