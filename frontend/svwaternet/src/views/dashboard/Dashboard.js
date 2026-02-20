import React, { useEffect, useMemo, useState } from 'react'
import { useSelector } from 'react-redux'
import { CCard, CCardBody, CCardHeader, CCol, CRow } from '@coreui/react'
import SimplifiedROSystem from '../../components/SimplifiedROSystem'
import { fetchLatestState } from '../../api/state'
import { subscribeLatestState } from '../../api/stateStream'

const Dashboard = () => {
  const selectedSystem = useSelector((state) => state.selectedSystem)
  const [latestState, setLatestState] = useState(null)
  const [loadingState, setLoadingState] = useState(true)
  const [stateError, setStateError] = useState('')

  const systemDetails = {
    Bluerock: {
      name: 'Bluerock Water Treatment System',
      description:
        'Live overview of the Bluerock RO facility, highlighting tank levels, treatment flow, and quality metrics.',
    },
    'Santa Teresa': {
      name: 'Santa Teresa Water Treatment System',
      description:
        'Main informational dashboard for the Santa Teresa RO system with real-time storage and quality indicators.',
    },
    'Pryor Farms': {
      name: 'Pryor Farms Water Treatment System',
      description:
        'Operational snapshot of the Pryor Farms treatment system with simplified RO flow and sensor highlights.',
    },
  }
  const currentSystem = systemDetails[selectedSystem] || systemDetails.Bluerock

  const siteKey = useMemo(() => {
    switch (selectedSystem) {
      case 'Santa Teresa':
        return 'santateresa'
      case 'Pryor Farms':
        return 'pryorfarm'
      case 'Bluerock':
      default:
        return 'bluerock'
    }
  }, [selectedSystem])

  useEffect(() => {
    const controller = new AbortController()
    let active = true

    setLoadingState(true)
    setStateError('')
    fetchLatestState(siteKey, { signal: controller.signal, soft: true })
      .then((payload) => {
        if (!active) return
        setLatestState(payload)
      })
      .catch((err) => {
        if (!active || err?.name === 'AbortError') return
        setStateError(err?.message || 'Failed to load latest state')
      })
      .finally(() => {
        if (!active) return
        setLoadingState(false)
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [siteKey])

  useEffect(() => {
    let active = true
    let ws = null
    let reconnectTimer = null
    let retryDelayMs = 1000

    const openSocket = () => {
      if (!active) return
      ws = subscribeLatestState(siteKey, {
        soft: true,
        onMessage: (payload) => {
          if (!active) return
          if (payload?.type === 'state.latest') {
            setLatestState({
              data: payload.data || {},
              meta: payload.meta || {},
            })
            setStateError('')
            setLoadingState(false)
          }
        },
        onError: () => {
          // onclose handles reconnect scheduling
        },
      })

      ws.onclose = () => {
        if (!active) return
        reconnectTimer = setTimeout(openSocket, retryDelayMs)
        retryDelayMs = Math.min(retryDelayMs * 2, 10000)
      }
    }

    openSocket()

    return () => {
      active = false
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        ws.close()
      }
    }
  }, [siteKey])

  const roRecovery = latestState?.data?.ro_recovery
  const hasRoRecovery = typeof roRecovery === 'number'

  return (
    <>
      <CRow className="mb-4">
        <CCol>
          <h2 className="mb-1">Home</h2>
          <div className="text-body-secondary">Basic System Overview</div>
        </CCol>
      </CRow>

      <CRow className="mb-4">
        <CCol>
          <CCard>
            <CCardHeader>System Overview</CCardHeader>
            <CCardBody>
              <h4 className="mb-2">{currentSystem.name}</h4>
              <p className="text-body-secondary mb-0">{currentSystem.description}</p>
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>

      <CRow>
        <CCol lg={7} className="mb-4 mb-lg-0">
          <CCard>
            <CCardHeader>Simplified RO System</CCardHeader>
            <CCardBody>
              <SimplifiedROSystem />
            </CCardBody>
          </CCard>
        </CCol>
        <CCol lg={5}>
          <CCard>
            <CCardHeader>Current State</CCardHeader>
            <CCardBody style={{ minHeight: 560 }}>
              {loadingState && <div className="text-body-secondary">Loading latest state...</div>}
              {stateError && <div className="text-danger">{stateError}</div>}
              {!loadingState && !stateError && (
                <>
                  <div className="mb-3">
                    <div className="text-body-secondary" style={{ fontSize: '0.85rem' }}>
                      Soft Sensor
                    </div>
                    <div className="fw-semibold" style={{ fontSize: '1.1rem' }}>
                      RO Recovery:{' '}
                      {hasRoRecovery ? `${Number(roRecovery).toFixed(2)}%` : 'Unavailable (check feedflow/permeateflow)'}
                    </div>
                  </div>
                  <pre
                    className="mb-0"
                    style={{
                      background: '#0f172a',
                      color: '#e2e8f0',
                      padding: '0.75rem',
                      borderRadius: 8,
                      fontSize: '0.8rem',
                      maxHeight: 460,
                      overflow: 'auto',
                    }}
                  >
                    {JSON.stringify(latestState, null, 2)}
                  </pre>
                </>
              )}
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>
    </>
  )
}

export default Dashboard
