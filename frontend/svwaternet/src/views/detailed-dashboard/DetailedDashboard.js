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
  CFormInput,
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

const SENSOR_META = {
  permeateflow: { label: 'Permeate Flow', unit: 'GPM', type: 'number' },
  feedflow: { label: 'Feed Flow', unit: 'GPM', type: 'number' },
  deliveryflow: { label: 'Delivery Flow', unit: 'GPM', type: 'number' },
  recycleflow: { label: 'Recycle Flow', unit: 'GPM', type: 'number' },
  inletflow: { label: 'Inlet Flow', unit: 'GPM', type: 'number' },
  feedtanklevel: { label: 'Feed Tank Level', unit: '%', type: 'number' },
  prodtanklevel: { label: 'Product Tank Level', unit: '%', type: 'number' },
  residualtanklevel: { label: 'Residual Tank Level', unit: '%', type: 'number' },
  permtds: { label: 'Permeate Conductivity', unit: 'uS', type: 'number' },
  feedtds: { label: 'Feed Conductivity', unit: 'uS', type: 'number' },
  permnitrate: { label: 'Permeate Nitrate', unit: 'mg/L', type: 'number' },
  permtemp: { label: 'Permeate Temperature', unit: 'C', type: 'number' },
  inletpressure: { label: 'Inlet Pressure', unit: 'PSI', type: 'number' },
  feedpressure: { label: 'Feed Pressure', unit: 'PSI', type: 'number' },
  ropressure: { label: 'RO Pressure', unit: 'PSI', type: 'number' },
  concentratepressure: { label: 'Concentrate Pressure', unit: 'PSI', type: 'number' },
  permeatepressure: { label: 'Permeate Pressure', unit: 'PSI', type: 'number' },
  deliverypressure: { label: 'Delivery Pressure', unit: 'PSI', type: 'number' },
  wellpumprun: { label: 'Well Pump', type: 'boolean' },
  feedpumprun: { label: 'P1 Feed Pump', type: 'boolean' },
  ropumprun: { label: 'P2 RO Pump', type: 'boolean' },
  deliveryrun: { label: 'P3 Delivery Pump', type: 'boolean' },
  inletrun: { label: 'AV1 Inlet Valve', type: 'boolean' },
  runflush: { label: 'AV2 Flush Valve', type: 'boolean' },
  concbypassrun: { label: 'AV5 Concentrate Bypass', type: 'boolean' },
  proddiversionrun: { label: 'AV6 Product Diversion', type: 'boolean' },
  residtankvalverun: { label: 'AV7 Residual Valve', type: 'boolean' },
}

const PRESETS = {
  '15m': { label: 'Past 15 Minutes', ms: 15 * 60 * 1000 },
  '1h': { label: 'Past 1 Hour', ms: 60 * 60 * 1000 },
  '6h': { label: 'Past 6 Hours', ms: 6 * 60 * 60 * 1000 },
  '24h': { label: 'Past 24 Hours', ms: 24 * 60 * 60 * 1000 },
  '7d': { label: 'Past 7 Days', ms: 7 * 24 * 60 * 60 * 1000 },
}

const DEFAULT_METRIC_KEY = 'permeateflow'

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
  let lo = 0
  let hi = rows.length - 1
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2)
    const midTs = toTs(rows[mid])
    if (midTs < ts) {
      lo = mid + 1
    } else if (midTs > ts) {
      hi = mid - 1
    } else {
      return rows[mid]
    }
  }

  if (lo >= rows.length) return rows[rows.length - 1]
  if (hi < 0) return rows[0]

  const loDist = Math.abs(toTs(rows[lo]) - ts)
  const hiDist = Math.abs(toTs(rows[hi]) - ts)
  if (loDist < hiDist) {
    return rows[lo]
  }
  return rows[hi]
}

function formatTsLabel(ts) {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function rangeBoundsFromPreset(preset) {
  const end = new Date()
  const start = new Date(end.getTime() - PRESETS[preset].ms)
  return { start: start.toISOString(), end: end.toISOString() }
}

function isoToLocalInputValue(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const offsetMs = d.getTimezoneOffset() * 60 * 1000
  const local = new Date(d.getTime() - offsetMs)
  return local.toISOString().slice(0, 16)
}

function localInputToISO(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return d.toISOString()
}

function inferSensorType(rows, key) {
  const configured = SENSOR_META[key]?.type
  if (configured) return configured
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    const v = rows[i]?.[key]
    if (typeof v === 'boolean') return 'boolean'
    if (typeof v === 'number') return 'number'
  }
  return 'number'
}

function sensorDisplayName(key) {
  if (!key) return 'Sensor'
  if (SENSOR_META[key]?.label) return SENSOR_META[key].label
  return key.replaceAll('_', ' ').replace(/\b\w/g, (m) => m.toUpperCase())
}

const buildLiveMd = (data = {}, onSelectSensor = () => {}) => ({
  get: (key, field) => {
    const value = data?.[key]
    if (field === 'abbreviated_name') return ABBR[key] || key?.slice(0, 3)?.toUpperCase() || ''
    if (field === 'units') return SENSOR_META[key]?.unit || ''
    if (field === 'current_value') return value ?? 0
    if (field === 'on_click') {
      if (!key || key === '???') return () => {}
      return () => onSelectSensor(key)
    }
    return ''
  },
})

const DetailedDashboard = () => {
  const selectedSystem = useSelector((state) => state.selectedSystem)
  const [timelineRows, setTimelineRows] = useState([])
  const [stateError, setStateError] = useState('')
  const [streamState, setStreamState] = useState('connecting')
  const [isLivePlaying, setIsLivePlaying] = useState(true)
  const [focusedTs, setFocusedTs] = useState(null)
  const [frozenTs, setFrozenTs] = useState(null)
  const [timePreset, setTimePreset] = useState('1h')
  const [showCustomRange, setShowCustomRange] = useState(false)
  const initialBounds = rangeBoundsFromPreset('1h')
  const [rangeStartInput, setRangeStartInput] = useState(isoToLocalInputValue(initialBounds.start))
  const [rangeEndInput, setRangeEndInput] = useState(isoToLocalInputValue(initialBounds.end))
  const [activeRange, setActiveRange] = useState({
    kind: 'preset',
    preset: '1h',
    start: initialBounds.start,
    end: initialBounds.end,
  })
  const [selectedMetricKey, setSelectedMetricKey] = useState(DEFAULT_METRIC_KEY)

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
  const selectedMetricType = useMemo(
    () => inferSensorType(timelineRows, selectedMetricKey),
    [timelineRows, selectedMetricKey],
  )
  const selectedMetricLabel = sensorDisplayName(selectedMetricKey)
  const selectedMetricUnit = SENSOR_META[selectedMetricKey]?.unit || ''

  const md = useMemo(
    () => buildLiveMd(data, setSelectedMetricKey),
    [data, setSelectedMetricKey],
  )

  useEffect(() => {
    const controller = new AbortController()

    fetchStateRange(siteKey, {
      signal: controller.signal,
      start: activeRange.start,
      end: activeRange.end,
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
  }, [siteKey, activeRange])

  useEffect(() => {
    let active = true
    let ws = null
    let reconnectTimer = null
    let retryDelayMs = 1000

    const openSocket = () => {
      if (!active) return
      setStreamState((prev) => (prev === 'connected' ? 'connected' : 'connecting'))
      ws = subscribeLatestState(siteKey, {
        soft: true,
        onOpen: () => {
          if (!active) return
          setStreamState('connected')
        },
        onMessage: (payload) => {
          if (!active || payload?.type !== 'state.latest' || !payload?.data) return
          setTimelineRows((prev) => mergeRows(prev, [payload.data]))
          setStateError('')
        },
      })

      ws.onclose = () => {
        if (!active) return
        setStreamState('reconnecting')
        reconnectTimer = setTimeout(openSocket, retryDelayMs)
        retryDelayMs = Math.min(retryDelayMs * 2, 10000)
      }
    }

    openSocket()
    return () => {
      active = false
      setStreamState('disconnected')
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        ws.close()
      }
    }
  }, [siteKey])

  useEffect(() => {
    const onKeyDown = (e) => {
      const tag = e.target?.tagName?.toLowerCase()
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return

      if (e.code === 'Space') {
        e.preventDefault()
        setIsLivePlaying((v) => !v)
        return
      }
      if (e.key?.toLowerCase() === 'l') {
        setFocusedTs(null)
        setFrozenTs(null)
        setIsLivePlaying(true)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

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
  const roRecovery =
    typeof data.ro_recovery === 'number' && Number.isFinite(data.ro_recovery) ? data.ro_recovery : null

  const chartPoints = timelineRows
    .map((row) => {
      const raw = row?.[selectedMetricKey]
      const val = selectedMetricType === 'boolean' ? (raw ? 1 : 0) : Number(raw ?? 0)
      return { ts: toTs(row), val }
    })
    .filter((p) => p.ts > 0)
  const focusedIndex = focusedTs ? chartPoints.findIndex((p) => p.ts === focusedTs) : -1

  const chartData = {
    labels: chartPoints.map((p) => formatTsLabel(p.ts)),
    datasets: [
      {
        label:
          selectedMetricType === 'boolean'
            ? `${selectedMetricLabel} (On/Off)`
            : `${selectedMetricLabel}${selectedMetricUnit ? ` (${selectedMetricUnit})` : ''}`,
        data: chartPoints.map((p) => p.val),
        borderColor: selectedMetricType === 'boolean' ? '#22c55e' : '#0ea5e9',
        backgroundColor:
          selectedMetricType === 'boolean' ? 'rgba(34,197,94,0.28)' : 'rgba(14,165,233,0.15)',
        pointHoverRadius: 4,
        pointBackgroundColor: chartPoints.map((_p, idx) =>
          idx === focusedIndex ? '#f59e0b' : selectedMetricType === 'boolean' ? '#22c55e' : '#0ea5e9',
        ),
        pointBorderColor: chartPoints.map((_p, idx) => (idx === focusedIndex ? '#f59e0b' : 'transparent')),
        pointRadius: chartPoints.map((_p, idx) => (idx === focusedIndex ? 4 : 0)),
        borderWidth: 2,
        fill: true,
        tension: selectedMetricType === 'boolean' ? 0 : 0.2,
        stepped: selectedMetricType === 'boolean' ? 'before' : false,
      },
    ],
  }

  const chartOptions = {
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    scales: {
      x: {
        ticks: { maxTicksLimit: 8 },
        grid: { color: 'rgba(120,120,120,0.15)' },
        title: { display: true, text: 'Time' },
      },
      y: {
        beginAtZero: true,
        suggestedMax: selectedMetricType === 'boolean' ? 1 : undefined,
        max: selectedMetricType === 'boolean' ? 1 : undefined,
        grid: { color: 'rgba(120,120,120,0.15)' },
        ticks:
          selectedMetricType === 'boolean'
            ? {
                stepSize: 1,
                callback: (value) => (Number(value) >= 1 ? 'On' : 'Off'),
              }
            : undefined,
        title: {
          display: true,
          text: selectedMetricType === 'boolean' ? 'State' : selectedMetricUnit || 'Value',
        },
      },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        mode: 'index',
        intersect: false,
        callbacks: {
          label: (ctx) => {
            if (selectedMetricType === 'boolean') {
              return `${selectedMetricLabel}: ${Number(ctx.parsed.y) > 0 ? 'On' : 'Off'}`
            }
            const v = Number(ctx.parsed.y)
            return `${selectedMetricLabel}: ${v.toFixed(2)}${selectedMetricUnit ? ` ${selectedMetricUnit}` : ''}`
          },
        },
      },
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

  const activeRangeLabel =
    activeRange.kind === 'preset'
      ? PRESETS[activeRange.preset]?.label || 'Preset'
      : `${new Date(activeRange.start).toLocaleString()} to ${new Date(activeRange.end).toLocaleString()}`

  const applyPreset = (preset) => {
    const bounds = rangeBoundsFromPreset(preset)
    setTimePreset(preset)
    setRangeStartInput(isoToLocalInputValue(bounds.start))
    setRangeEndInput(isoToLocalInputValue(bounds.end))
    setActiveRange({ kind: 'preset', preset, start: bounds.start, end: bounds.end })
  }

  const applyCustomRange = () => {
    const start = localInputToISO(rangeStartInput)
    const end = localInputToISO(rangeEndInput)
    if (!start || !end) {
      setStateError('Invalid custom time range')
      return
    }
    if (new Date(start).getTime() >= new Date(end).getTime()) {
      setStateError('Range start must be before end')
      return
    }
    setStateError('')
    setActiveRange({ kind: 'custom', preset: null, start, end })
  }

  const streamBadge =
    streamState === 'connected' ? (
      <CBadge color="success">Connected</CBadge>
    ) : streamState === 'reconnecting' || streamState === 'connecting' ? (
      <CBadge color="warning">Reconnecting...</CBadge>
    ) : (
      <CBadge color="secondary">Disconnected</CBadge>
    )

  return (
    <>
      <CRow className="mb-3">
        <CCol>
          <CCard>
            <CCardBody style={{ paddingTop: '0.75rem', paddingBottom: '0.75rem' }}>
              <div className="d-flex flex-wrap align-items-end gap-2">
                <div className="d-flex align-items-center me-2">
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
                <div style={{ minWidth: 190 }}>
                  <CFormSelect
                    size="sm"
                    value={timePreset}
                    onChange={(e) => applyPreset(e.target.value)}
                    options={Object.entries(PRESETS).map(([value, cfg]) => ({ value, label: cfg.label }))}
                  />
                </div>
                <CButton color="secondary" variant="outline" size="sm" onClick={applyCustomRange}>
                  Apply
                </CButton>
                <CButton color="secondary" variant="ghost" size="sm" onClick={() => applyPreset(timePreset)}>
                  Reset
                </CButton>
                <CButton
                  color="secondary"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowCustomRange((v) => !v)}
                >
                  {showCustomRange ? 'Hide Custom' : 'Custom Range'}
                </CButton>
                <CButton
                  color={isLivePlaying ? 'primary' : 'secondary'}
                  variant={isLivePlaying ? undefined : 'outline'}
                  size="sm"
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
                    size="sm"
                    onClick={() => {
                      setFocusedTs(null)
                      setFrozenTs(null)
                      setIsLivePlaying(true)
                    }}
                  >
                    Back to Live
                  </CButton>
                )}
                <CBadge color={focusedTs ? 'warning' : isLivePlaying ? 'success' : 'secondary'}>
                  {focusedTs ? 'FOCUSED' : isLivePlaying ? 'LIVE' : 'PAUSED'}
                </CBadge>
                {streamBadge}
                <div className="small text-body-secondary ms-auto">{activeRangeLabel} (UTC)</div>
              </div>
              {showCustomRange && (
                <div className="d-flex flex-wrap align-items-center gap-2 mt-2">
                  <div style={{ minWidth: 190 }}>
                    <CFormInput
                      size="sm"
                      type="datetime-local"
                      value={rangeStartInput}
                      onChange={(e) => setRangeStartInput(e.target.value)}
                    />
                  </div>
                  <div style={{ minWidth: 190 }}>
                    <CFormInput
                      size="sm"
                      type="datetime-local"
                      value={rangeEndInput}
                      onChange={(e) => setRangeEndInput(e.target.value)}
                    />
                  </div>
                  <div className="small text-body-secondary ms-1">Shortcuts: `Space` pause/play, `L` live</div>
                </div>
              )}
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>

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
            <CCardHeader>Sensor Status</CCardHeader>
            <CCardBody>
              <div className="small text-body-secondary mb-2">System Summary</div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>RO Recovery</span>
                <span className="fw-semibold">
                  {roRecovery === null ? 'N/A' : `${roRecovery.toFixed(2)}%`}
                </span>
              </div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>Alarm</span>
                {boolBadge(data.alarm, 'Active', 'Clear')}
              </div>
              <div className="d-flex justify-content-between align-items-center mb-3">
                <span>Lockout</span>
                {boolBadge(data.lockout, 'Locked', 'Normal')}
              </div>
              <hr className="my-2" />
              <div className="small text-body-secondary mb-2">Pump and Valve States</div>
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
              Live Trend - {selectedMetricLabel}
              {!focusedTs && isLivePlaying && (
                <span className="ms-2 text-body-secondary" style={{ fontSize: '0.85rem' }}>
                  Following latest
                </span>
              )}
              {focusedTs && (
                <span className="ms-2 text-body-secondary" style={{ fontSize: '0.85rem' }}>
                  Focused at {new Date(focusedTs).toLocaleString()}
                </span>
              )}
              {focusedTs && (
                <CButton
                  color="success"
                  variant="outline"
                  size="sm"
                  className="ms-2"
                  onClick={() => {
                    setFocusedTs(null)
                    setFrozenTs(null)
                    setIsLivePlaying(true)
                  }}
                >
                  Back to Live
                </CButton>
              )}
            </CCardHeader>
            <CCardBody>
              <div style={{ height: 320 }}>
                {chartPoints.length === 0 ? (
                  <div className="h-100 d-flex flex-column align-items-center justify-content-center text-body-secondary">
                    <div className="mb-1">No data in this window.</div>
                    <div className="small">Try 24h/7d preset or apply a wider custom range.</div>
                  </div>
                ) : (
                  <CChartLine data={chartData} options={chartOptions} />
                )}
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
