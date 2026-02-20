import React, { useEffect, useMemo, useState } from 'react'
import { useSelector } from 'react-redux'
import {
  CBadge,
  CButton,
  CCard,
  CCardBody,
  CCardHeader,
  CCol,
  CFormCheck,
  CFormSelect,
  CRow,
} from '@coreui/react'
import { CChartLine } from '@coreui/react-chartjs'

import BluerockSchematic from '../../components/detailed/BluerockSchematic'
import SantaTeresaPryorFarmsSchematic from '../../components/detailed/SantaTeresaPryorFarmsSchematic'
import PryorFarmsSchematic from '../../components/detailed/PryorFarmsSchematic'
import { fetchStateRange } from '../../api/state'
import { subscribeLatestState } from '../../api/stateStream'

const ABBR = {
  feedtanklevel: 'LT1',
  prodtanklevel: 'LT2',
  residualtanklevel: 'LT3',
  flushtanklevel: 'LT4',
  wellpumprun: 'WP',
  feedpumprun: 'P1',
  ropumprun: 'P2',
  deliveryrun: 'P3',
  inletrun: 'AV1',
  runflush: 'AV2',
  ropressctrlvalveposition: 'AV3',
  recyclevalveposition: 'AV4',
  concbypassrun: 'AV5',
  proddiversionrun: 'AV6',
  residtankvalverun: 'AV7',
  inletpressure: 'PT1',
  feedpressure: 'PT2',
  ropressure: 'PT3',
  concentratepressure: 'PT4',
  permeatepressure: 'PT5',
  deliverypressure: 'PT6',
  recycleflow: 'FT2',
  feedflow: 'FT1',
  inletflow: 'FT0',
  permeateflow: 'FT3',
  deliveryflow: 'FT4',
  concentrateflow: 'FT5',
  feedtds: 'CT1',
  permtds: 'CTP',
  permnitrate: 'NT1',
  permtemp: 'TT1',
}

const PRESETS = {
  '15m': { label: 'Past 15 Minutes', ms: 15 * 60 * 1000 },
  '1h': { label: 'Past 1 Hour', ms: 60 * 60 * 1000 },
  '6h': { label: 'Past 6 Hours', ms: 6 * 60 * 60 * 1000 },
  '24h': { label: 'Past 24 Hours', ms: 24 * 60 * 60 * 1000 },
}

const METRIC_KEY = 'permeateflow'

function toTs(row) {
  const raw = row?.recordtime || row?.plctime
  if (!raw) return 0
  const t = new Date(raw).getTime()
  return Number.isNaN(t) ? 0 : t
}

function rowKey(row) {
  const ts = toTs(row)
  const id = row?.id ?? ''
  return `${id}:${ts}`
}

function mergeRows(prev, incoming) {
  const merged = [...prev]
  const indexByKey = new Map(prev.map((r, i) => [rowKey(r), i]))
  for (const row of incoming) {
    const key = rowKey(row)
    const idx = indexByKey.get(key)
    if (idx === undefined) {
      merged.push(row)
      indexByKey.set(key, merged.length - 1)
    } else {
      merged[idx] = row
    }
  }
  merged.sort((a, b) => toTs(a) - toTs(b))
  if (merged.length > 3000) {
    return merged.slice(merged.length - 3000)
  }
  return merged
}

function nearestRow(rows, ts) {
  if (!rows.length) return null
  let best = rows[0]
  let bestDist = Math.abs(toTs(best) - ts)
  for (let i = 1; i < rows.length; i += 1) {
    const dist = Math.abs(toTs(rows[i]) - ts)
    if (dist < bestDist) {
      best = rows[i]
      bestDist = dist
    }
  }
  return best
}

function formatTsLabel(ts) {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function rangeBoundsFromPreset(preset) {
  const end = new Date()
  const start = new Date(end.getTime() - PRESETS[preset].ms)
  return { start: start.toISOString(), end: end.toISOString() }
}

const buildLiveMd = (data = {}) => ({
  get: (key, field) => {
    const value = data?.[key]
    if (field === 'abbreviated_name') return ABBR[key] || key?.slice(0, 3)?.toUpperCase() || ''
    if (field === 'units') return ''
    if (field === 'current_value') return value ?? 0
    if (field === 'on_click') return () => {}
    return ''
  },
})

const DetailedDashboard = () => {
  const selectedSystem = useSelector((state) => state.selectedSystem)
  const [timelineRows, setTimelineRows] = useState([])
  const [stateError, setStateError] = useState('')
  const [isLivePlaying, setIsLivePlaying] = useState(true)
  const [focusedTs, setFocusedTs] = useState(null)
  const [frozenTs, setFrozenTs] = useState(null)
  const [timePreset, setTimePreset] = useState('1h')

  const siteKey =
    selectedSystem === 'Bluerock'
      ? 'bluerock'
      : selectedSystem === 'Pryor Farms'
        ? 'pryorfarm'
        : 'santateresa'

  const Schematic =
    selectedSystem === 'Bluerock'
      ? BluerockSchematic
      : selectedSystem === 'Pryor Farms'
        ? PryorFarmsSchematic
        : SantaTeresaPryorFarmsSchematic

  const latestRow = timelineRows.length ? timelineRows[timelineRows.length - 1] : null
  const activeTs = focusedTs ?? (isLivePlaying ? toTs(latestRow) : frozenTs)
  const activeRow = activeTs ? nearestRow(timelineRows, activeTs) : latestRow
  const data = activeRow || {}
  const md = useMemo(() => buildLiveMd(data), [data])

  useEffect(() => {
    const controller = new AbortController()
    const bounds = rangeBoundsFromPreset(timePreset)

    fetchStateRange(siteKey, {
      signal: controller.signal,
      start: bounds.start,
      end: bounds.end,
      soft: true,
    })
      .then((payload) => {
        const rows = Array.isArray(payload?.data) ? payload.data : []
        setTimelineRows(rows)
        setFocusedTs(null)
        setFrozenTs(rows.length ? toTs(rows[rows.length - 1]) : null)
        setStateError('')
      })
      .catch((err) => {
        if (err?.name === 'AbortError') return
        setStateError(err?.message || 'Failed to load time range')
      })

    return () => controller.abort()
  }, [siteKey, timePreset])

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
          if (!active || payload?.type !== 'state.latest' || !payload?.data) return
          setTimelineRows((prev) => mergeRows(prev, [payload.data]))
          setStateError('')
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

  useEffect(() => {
    if (isLivePlaying) {
      setFrozenTs(null)
      return
    }
    if (!focusedTs && latestRow) {
      setFrozenTs(toTs(latestRow))
    }
  }, [isLivePlaying, focusedTs, latestRow])

  const boolBadge = (value, trueText = 'Running', falseText = 'Not Running') => {
    if (value) return <CBadge color="success">{trueText}</CBadge>
    return <CBadge color="danger">{falseText}</CBadge>
  }

  const roStatusBadge = () => {
    if (data.rostandby) return <CBadge color="warning">RO Standby</CBadge>
    if (data.ropumprun) return <CBadge color="success">RO Running</CBadge>
    return <CBadge color="danger">RO Offline</CBadge>
  }

  const warnings = []
  if (data.alarm) warnings.push('Alarm Active')
  if ((data.warnword0 || 0) > 0) warnings.push(`Warn Word 0: ${data.warnword0}`)
  if ((data.warnword1 || 0) > 0) warnings.push(`Warn Word 1: ${data.warnword1}`)
  if (data.lockout) warnings.push('System Lockout')
  if (stateError) warnings.push(`Data stream error: ${stateError}`)

  const chartPoints = timelineRows
    .map((row) => ({ ts: toTs(row), val: Number(row?.[METRIC_KEY] ?? 0) }))
    .filter((p) => p.ts > 0)

  const chartData = {
    labels: chartPoints.map((p) => formatTsLabel(p.ts)),
    datasets: [
      {
        label: 'Permeate Flow (GPM)',
        data: chartPoints.map((p) => p.val),
        borderColor: '#0ea5e9',
        backgroundColor: 'rgba(14,165,233,0.15)',
        pointRadius: 0,
        pointHoverRadius: 4,
        borderWidth: 2,
        fill: true,
        tension: 0.2,
      },
    ],
  }

  const chartOptions = {
    maintainAspectRatio: false,
    interaction: { mode: 'nearest', intersect: false },
    scales: {
      x: {
        ticks: { maxTicksLimit: 8 },
        grid: { color: 'rgba(120,120,120,0.15)' },
      },
      y: {
        beginAtZero: true,
        grid: { color: 'rgba(120,120,120,0.15)' },
      },
    },
    plugins: {
      legend: { display: false },
      tooltip: { mode: 'index', intersect: false },
    },
    onClick: (_event, elements) => {
      if (!elements?.length) return
      const idx = elements[0].index
      const p = chartPoints[idx]
      if (!p) return
      setFocusedTs(p.ts)
      setIsLivePlaying(false)
    },
  }

  const activeRangeLabel = PRESETS[timePreset]?.label || 'Custom Range'

  return (
    <>
      <CRow className="mb-4">
        <CCol lg={8} className="mb-4 mb-lg-0">
          <CCard className="detailed-schematic-card">
            <CCardHeader>Detailed Process Flow</CCardHeader>
            <CCardBody className="detailed-schematic-body">
              <div className="w-100" style={{ height: 500 }}>
                <Schematic md={md} />
              </div>
            </CCardBody>
          </CCard>
        </CCol>
        <CCol lg={4}>
          <CCard>
            <CCardHeader>Time Controls</CCardHeader>
            <CCardBody>
              <div className="d-flex align-items-center gap-2 mb-3">
                <CFormCheck
                  id="liveData"
                  label="Live Data"
                  checked={isLivePlaying}
                  onChange={(e) => {
                    const next = e.target.checked
                    setIsLivePlaying(next)
                    if (next) {
                      setFocusedTs(null)
                      setFrozenTs(null)
                    }
                  }}
                />
              </div>
              <div className="d-flex align-items-center gap-2 mb-2">
                <CFormSelect
                  value={timePreset}
                  onChange={(e) => setTimePreset(e.target.value)}
                  options={Object.entries(PRESETS).map(([value, cfg]) => ({ value, label: cfg.label }))}
                />
              </div>
              <div className="small text-body-secondary mb-3">{activeRangeLabel} (UTC)</div>
              <div className="d-flex gap-2">
                <CButton
                  color={isLivePlaying ? 'primary' : 'secondary'}
                  variant={isLivePlaying ? undefined : 'outline'}
                  onClick={() => {
                    setIsLivePlaying((v) => !v)
                    if (!isLivePlaying) {
                      setFocusedTs(null)
                    }
                  }}
                >
                  {isLivePlaying ? 'Pause' : 'Play'}
                </CButton>
                {!isLivePlaying && (
                  <CButton
                    color="success"
                    variant="outline"
                    onClick={() => {
                      setFocusedTs(null)
                      setFrozenTs(null)
                      setIsLivePlaying(true)
                    }}
                  >
                    Back to Live
                  </CButton>
                )}
              </div>
            </CCardBody>
          </CCard>
          <CCard className="mt-4">
            <CCardHeader>Sensor Status</CCardHeader>
            <CCardBody>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>RO Status</span>
                {roStatusBadge()}
              </div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>Well Pump</span>
                {boolBadge(data.wellpumprun)}
              </div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>P1 Feed Pump</span>
                {boolBadge(data.feedpumprun)}
              </div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>AV1 Inlet Valve</span>
                {boolBadge(data.inletrun, 'Open', 'Closed')}
              </div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>P2 RO Pump</span>
                {boolBadge(data.ropumprun)}
              </div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>AV6 Product Diversion Valve</span>
                {boolBadge(data.proddiversionrun, 'To Product Tank', 'Divert to Residual Line')}
              </div>
              <div className="d-flex justify-content-between align-items-center">
                <span>P3 Delivery Pump</span>
                {boolBadge(data.deliveryrun)}
              </div>
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>

      <CRow className="mb-4">
        <CCol>
          <CCard>
            <CCardHeader>
              Live Trend - Permeate Flow
              {focusedTs && (
                <span className="ms-2 text-body-secondary" style={{ fontSize: '0.85rem' }}>
                  Focused at {new Date(focusedTs).toLocaleString()}
                </span>
              )}
            </CCardHeader>
            <CCardBody>
              <div style={{ height: 260 }}>
                <CChartLine data={chartData} options={chartOptions} />
              </div>
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>

      <CRow>
        <CCol>
          <CCard>
            <CCardHeader>Current Warnings</CCardHeader>
            <CCardBody className="text-body-secondary">
              <ul className="mb-0">
                {warnings.length === 0 && <li>No active warnings.</li>}
                {warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>
    </>
  )
}

export default DetailedDashboard
