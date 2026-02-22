import React, { useEffect, useMemo, useState } from 'react'
import { useSelector } from 'react-redux'
import { CCard, CCardBody, CCardHeader, CCol, CRow } from '@coreui/react'
import SimplifiedROSystem from '../../components/SimplifiedROSystem'
import { fetchDailySummary, fetchLatestState } from '../../api/state'
import { subscribeLatestState } from '../../api/stateStream'

const DASHBOARD_LATEST_CACHE_PREFIX = 'svwn_dashboard_latest_v1:'

function readDashboardLatestCache(siteKey) {
  if (typeof window === 'undefined' || !siteKey) return null
  try {
    const raw = window.sessionStorage.getItem(`${DASHBOARD_LATEST_CACHE_PREFIX}${siteKey}`)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || !parsed.data || typeof parsed.data !== 'object') return null
    return parsed
  } catch {
    return null
  }
}

function writeDashboardLatestCache(siteKey, payload) {
  if (typeof window === 'undefined' || !siteKey || !payload) return
  try {
    window.sessionStorage.setItem(`${DASHBOARD_LATEST_CACHE_PREFIX}${siteKey}`, JSON.stringify(payload))
  } catch {
    // ignore storage errors (quota/private mode)
  }
}

const SIMPLIFIED_ABBR = {
  feedtanklevel: 'LT1',
  prodtanklevel: 'LT2',
  producttanklevel: 'LT2',
  feedpumprun: 'P1',
  ropumprun: 'P2',
  rorun: 'P2',
  permtds: 'CTP',
  permnitrate: 'NTP',
}

const SIMPLIFIED_UNITS = {
  feedtanklevel: '%',
  prodtanklevel: '%',
  producttanklevel: '%',
  permtds: 'uS',
  permnitrate: 'mg/L',
}

function buildSimplifiedMd(data = {}) {
  return {
    get: (key, field) => {
      if (field === 'current_value') return data?.[key]
      if (field === 'abbreviated_name') return SIMPLIFIED_ABBR[key] || key?.slice(0, 3)?.toUpperCase() || ''
      if (field === 'units') return SIMPLIFIED_UNITS[key] || ''
      if (field === 'is_selected') return false
      if (field === 'on_click') return () => {}
      return ''
    },
  }
}

const Dashboard = () => {
  const selectedSystem = useSelector((state) => state.selectedSystem)
  const [latestState, setLatestState] = useState(null)
  const [loadingState, setLoadingState] = useState(true)
  const [stateError, setStateError] = useState('')
  const [dailySummary, setDailySummary] = useState(null)
  const [dailySummaryError, setDailySummaryError] = useState('')

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
    const cached = readDashboardLatestCache(siteKey)
    if (cached) {
      setLatestState(cached)
      setLoadingState(false)
      setStateError('')
    } else {
      setLatestState(null)
    }
  }, [siteKey])

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setDailySummaryError('')
    fetchDailySummary(siteKey, { signal: controller.signal })
      .then((payload) => {
        if (!active) return
        setDailySummary(payload)
      })
      .catch((err) => {
        if (!active || err?.name === 'AbortError') return
        setDailySummary(null)
        setDailySummaryError(err?.message || 'Failed to load daily summary')
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [siteKey])

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    const hasCached = Boolean(readDashboardLatestCache(siteKey))

    setLoadingState(!hasCached)
    setStateError('')
    fetchLatestState(siteKey, { signal: controller.signal, soft: true })
      .then((payload) => {
        if (!active) return
        setLatestState(payload)
        writeDashboardLatestCache(siteKey, payload)
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
            const next = {
              data: payload.data || {},
              meta: payload.meta || {},
            }
            setLatestState(next)
            writeDashboardLatestCache(siteKey, next)
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

  const dailyPermFlow = latestState?.data?.dailypermflow
  const hasDailyPermFlow = typeof dailyPermFlow === 'number' && Number.isFinite(dailyPermFlow)
  const stateCode = latestState?.data?.state
  const stateLabel =
    stateCode === 0
      ? 'RO Off'
      : stateCode === 1
        ? 'E-Stop Pressed'
        : stateCode === 2
          ? 'RO Running'
          : stateCode === 3
            ? 'RO Standby'
            : stateCode === 5 || stateCode === 8
              ? 'Flushing'
              : 'Unknown'
  const lastUpdatedRaw = latestState?.data?.plctime || latestState?.data?.recordtime
  const lastUpdated = lastUpdatedRaw ? new Date(lastUpdatedRaw) : null
  const hasLastUpdated = Boolean(lastUpdated && !Number.isNaN(lastUpdated.getTime()))
  const simplifiedMd = useMemo(() => buildSimplifiedMd(latestState?.data || {}), [latestState])
  const summaryData = dailySummary?.data || {}
  const fmtNum = (value, suffix = '') =>
    typeof value === 'number' && Number.isFinite(value)
      ? `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix ? ` ${suffix}` : ''}`
      : 'Unavailable'

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
              <SimplifiedROSystem md={simplifiedMd} />
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
                  <div className="mb-4">
                    <div className="mb-2 fw-semibold" style={{ fontSize: '1.25rem', lineHeight: 1.25 }}>
                      Current State: {stateLabel}
                    </div>
                    <div className="text-body-secondary" style={{ fontSize: '1.05rem', lineHeight: 1.25 }}>
                      Last Updated:{' '}
                      {hasLastUpdated
                        ? lastUpdated.toLocaleString(undefined, {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric',
                            hour: 'numeric',
                            minute: '2-digit',
                            second: '2-digit',
                          })
                        : 'Unavailable'}
                    </div>
                  </div>
                  <div className="text-body-secondary" style={{ fontSize: '0.85rem' }}>
                    Daily Permeate Flow
                  </div>
                  <div className="fw-semibold" style={{ fontSize: '1.1rem' }}>
                    {hasDailyPermFlow
                      ? `${Number(dailyPermFlow).toLocaleString(undefined, { maximumFractionDigits: 2 })} gallons`
                      : 'Unavailable'}
                  </div>
                  <hr className="my-4" />
                  <div className="text-body-secondary mb-2" style={{ fontSize: '0.85rem' }}>
                    Daily Operational Metrics (Midnight Pacific to now)
                  </div>
                  {dailySummaryError && (
                    <div className="text-danger mb-2" style={{ fontSize: '0.9rem' }}>
                      {dailySummaryError}
                    </div>
                  )}
                  <div className="d-flex justify-content-between mb-2">
                    <span className="text-body-secondary">RO Feed Inflow</span>
                    <span className="fw-semibold">{fmtNum(summaryData.feed_gallons, 'gallons')}</span>
                  </div>
                  <div className="d-flex justify-content-between mb-2">
                    <span className="text-body-secondary">Permeate Production</span>
                    <span className="fw-semibold">{fmtNum(summaryData.permeate_gallons, 'gallons')}</span>
                  </div>
                  <div className="d-flex justify-content-between mb-2">
                    <span className="text-body-secondary">Energy Usage</span>
                    <span className="fw-semibold">{fmtNum(summaryData.energy_kwh, 'kWh')}</span>
                  </div>
                  <div className="d-flex justify-content-between mb-2">
                    <span className="text-body-secondary">Specific Energy</span>
                    <span className="fw-semibold">
                      {fmtNum(summaryData.specific_energy_kwh_per_1000g, 'kWh/1000-gallon')}
                    </span>
                  </div>
                  <div className="d-flex justify-content-between">
                    <span className="text-body-secondary">Estimated Cost / 1000 gal</span>
                    <span className="fw-semibold">
                      {summaryData.estimated_cost_per_1000g_usd == null
                        ? 'TBD'
                        : fmtNum(summaryData.estimated_cost_per_1000g_usd, 'USD')}
                    </span>
                  </div>
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
