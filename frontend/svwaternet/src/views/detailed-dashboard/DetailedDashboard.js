import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
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
import SantaTeresaSchematic from '../../components/detailed/SantaTeresaSchematic'
import PryorFarmsSchematic from '../../components/detailed/PryorFarmsSchematic'
import { fetchStateRange } from '../../api/state'
import { subscribeLatestState } from '../../api/stateStream'
import { bitTables, decodeBitfield } from '../../utils/bitfields'

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
const SITE_TO_SYSTEM = {
  bluerock: 'Bluerock',
  santateresa: 'Santa Teresa',
  pryorfarm: 'Pryor Farms',
}

function toTs(row) {
  const raw = row?.plctime || row?.recordtime
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

function getHashParams() {
  const hash = window.location.hash || ''
  const queryStart = hash.indexOf('?')
  if (queryStart < 0) return new URLSearchParams()
  return new URLSearchParams(hash.slice(queryStart + 1))
}

function pushHashParams(params) {
  const hash = window.location.hash || '#/detailed-dashboard'
  const queryStart = hash.indexOf('?')
  const path = queryStart >= 0 ? hash.slice(0, queryStart) : hash
  const qs = params.toString()
  const nextHash = qs ? `${path}?${qs}` : path
  const nextUrl = `${window.location.pathname}${window.location.search}${nextHash}`
  const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`
  if (currentUrl === nextUrl) return
  window.history.pushState(null, '', nextUrl)
}

function parseURLState() {
  const params = getHashParams()
  const siteParam = (params.get('site') || '').toLowerCase()
  const presetParam = params.get('preset')
  const hasPreset = Boolean(presetParam && PRESETS[presetParam])

  const startParam = params.get('start')
  const endParam = params.get('end')
  const startTs = startParam ? new Date(startParam).getTime() : NaN
  const endTs = endParam ? new Date(endParam).getTime() : NaN
  const hasRange = Number.isFinite(startTs) && Number.isFinite(endTs) && startTs < endTs

  const liveParam = params.get('live')
  const live = liveParam === '0' || liveParam === 'false' ? false : true

  const focusParam = params.get('focus')
  const focusTs = focusParam ? new Date(focusParam).getTime() : NaN

  return {
    siteParam,
    presetParam,
    hasPreset,
    hasRange,
    startISO: hasRange ? new Date(startTs).toISOString() : '',
    endISO: hasRange ? new Date(endTs).toISOString() : '',
    metric: params.get('metric') || '',
    live,
    focusTs: Number.isFinite(focusTs) ? focusTs : null,
  }
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

function firstFiniteNumber(...values) {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return value
  }
  return null
}

function formatSnapshotNumber(value, fractionDigits = 0) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'N/A'
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: fractionDigits,
  })
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
  const dispatch = useDispatch()
  const selectedSystem = useSelector((state) => state.selectedSystem)
  const [timelineRows, setTimelineRows] = useState([])
  const [stateError, setStateError] = useState('')
  const [streamState, setStreamState] = useState('connecting')
  const [isLivePlaying, setIsLivePlaying] = useState(true)
  const [focusedTs, setFocusedTs] = useState(null)
  const [hoverTs, setHoverTs] = useState(null)
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
  const [urlStateReady, setURLStateReady] = useState(false)
  const [dragSelect, setDragSelect] = useState(null)
  const [isPlaybackRunning, setIsPlaybackRunning] = useState(false)
  const chartRef = useRef(null)
  const suppressNextChartClickRef = useRef(false)
  const playbackTimerRef = useRef(null)

  const siteKey =
    selectedSystem === 'Bluerock'
      ? 'bluerock'
      : selectedSystem === 'Pryor Farms'
        ? 'pryorfarm'
      : 'santateresa'

  useEffect(() => {
    const applyFromURL = () => {
      const parsed = parseURLState()
      if (SITE_TO_SYSTEM[parsed.siteParam] && SITE_TO_SYSTEM[parsed.siteParam] !== selectedSystem) {
        dispatch({ type: 'set', selectedSystem: SITE_TO_SYSTEM[parsed.siteParam] })
      }

      if (parsed.hasPreset) {
        setTimePreset(parsed.presetParam)
      }

      if (parsed.hasRange) {
        const startISO = parsed.startISO
        const endISO = parsed.endISO
        const kind = parsed.hasPreset ? 'preset' : 'custom'
        setActiveRange({
          kind,
          preset: kind === 'preset' ? parsed.presetParam : null,
          start: startISO,
          end: endISO,
        })
        setRangeStartInput(isoToLocalInputValue(startISO))
        setRangeEndInput(isoToLocalInputValue(endISO))
      } else if (parsed.hasPreset) {
        const bounds = rangeBoundsFromPreset(parsed.presetParam)
        setActiveRange({ kind: 'preset', preset: parsed.presetParam, start: bounds.start, end: bounds.end })
        setRangeStartInput(isoToLocalInputValue(bounds.start))
        setRangeEndInput(isoToLocalInputValue(bounds.end))
      }

      if (parsed.metric) {
        setSelectedMetricKey(parsed.metric)
      }

      setIsLivePlaying(parsed.live)
      if (parsed.live) {
        setFocusedTs(null)
      } else if (parsed.focusTs) {
        setFocusedTs(parsed.focusTs)
        setIsLivePlaying(false)
      } else {
        setFocusedTs(null)
      }
    }

    applyFromURL()
    const onNav = () => applyFromURL()
    window.addEventListener('popstate', onNav)
    window.addEventListener('hashchange', onNav)

    setURLStateReady(true)
    return () => {
      window.removeEventListener('popstate', onNav)
      window.removeEventListener('hashchange', onNav)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch])

  useEffect(() => {
    if (!urlStateReady) return
    const params = new URLSearchParams()
    params.set('site', siteKey)
    params.set('live', isLivePlaying ? '1' : '0')
    params.set('start', activeRange.start)
    params.set('end', activeRange.end)
    params.set('metric', selectedMetricKey)
    if (activeRange.kind === 'preset' && activeRange.preset) {
      params.set('preset', activeRange.preset)
    }
    if (!isLivePlaying && focusedTs) {
      params.set('focus', new Date(focusedTs).toISOString())
    }
    pushHashParams(params)
  }, [urlStateReady, siteKey, isLivePlaying, activeRange, selectedMetricKey, focusedTs])

  const Schematic =
    selectedSystem === 'Bluerock'
      ? BluerockSchematic
      : selectedSystem === 'Pryor Farms'
        ? PryorFarmsSchematic
        : SantaTeresaSchematic

  const latestRow = timelineRows.length ? timelineRows[timelineRows.length - 1] : null
  const activeTs = hoverTs ?? focusedTs ?? (isLivePlaying ? toTs(latestRow) : frozenTs)
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

  useEffect(() => {
    return () => clearPlaybackTimer()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    stopPlayback()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteKey, activeRange, selectedMetricKey])

  const boolBadge = (value, trueText = 'Running', falseText = 'Not Running') => {
    if (value) return <CBadge color="success">{trueText}</CBadge>
    return <CBadge color="danger">{falseText}</CBadge>
  }

  const roStatusBadge = () => {
    const stateCode = Number.isInteger(data.state) ? data.state : null
    if (stateCode === 0) return <CBadge color="danger">RO Off</CBadge>
    if (stateCode === 1) return <CBadge color="danger">EStop Pressed!</CBadge>
    if (stateCode === 2) return <CBadge color="success">RO Running</CBadge>
    if (stateCode === 3) return <CBadge color="warning">RO Standby</CBadge>
    if (stateCode === 5 || stateCode === 8) return <CBadge color="info">Flushing</CBadge>
    return <CBadge color="secondary">Unknown</CBadge>
  }

  const warnings = []
  const decodedAlarmBits = decodeBitfield(Number(data.alarmword || 0), bitTables.alarm)
  const decodedWarn0Bits = decodeBitfield(Number(data.warnword0 || 0), bitTables.warning1)
  const decodedWarn1Bits = decodeBitfield(Number(data.warnword1 || 0), bitTables.warning2)
  const registerWarnings = Array.from(new Set([...decodedAlarmBits, ...decodedWarn0Bits, ...decodedWarn1Bits]))
  if (data.alarm) warnings.push('Alarm Active')
  registerWarnings.forEach((label) => warnings.push(label))
  if (stateError) warnings.push(`Data stream error: ${stateError}`)
  const totalROFlow = firstFiniteNumber(data.totalroflow)
  const totalFeedOrInletFlow = firstFiniteNumber(data.totalfeedflow, data.totalinletflow)
  const totalRecycleOrConcFlow = firstFiniteNumber(data.totalrecycleflow, data.totalconcflow)
  const totalDeliveryFlow = firstFiniteNumber(data.totaldelflow)
  const powerMeter = firstFiniteNumber(data.powermeter)
  const chartPoints = timelineRows
    .map((row) => {
      const raw = row?.[selectedMetricKey]
      const val = selectedMetricType === 'boolean' ? (raw ? 1 : 0) : Number(raw ?? 0)
      return { ts: toTs(row), val }
    })
    .filter((p) => p.ts > 0)
  const focusedIndex = focusedTs ? chartPoints.findIndex((p) => p.ts === focusedTs) : -1
  const hoverIndex = hoverTs ? chartPoints.findIndex((p) => p.ts === hoverTs) : -1

  function clearPlaybackTimer() {
    if (playbackTimerRef.current) {
      clearInterval(playbackTimerRef.current)
      playbackTimerRef.current = null
    }
  }

  function stopPlayback() {
    clearPlaybackTimer()
    setIsPlaybackRunning(false)
  }

  function startPlayback() {
    if (chartPoints.length < 2) return
    clearPlaybackTimer()
    setIsPlaybackRunning(true)
    setIsLivePlaying(false)
    setFocusedTs(null)

    const targetFrames = 100
    const seqLength = Math.min(targetFrames, chartPoints.length)
    const sequence = Array.from({ length: seqLength }, (_v, i) => {
      const idx = Math.round((i * (chartPoints.length - 1)) / Math.max(1, seqLength - 1))
      return chartPoints[idx].ts
    })
    let cursor = 0
    setFocusedTs(sequence[cursor])
    setFrozenTs(sequence[cursor])

    const intervalMs = Math.max(20, Math.floor(10000 / Math.max(1, sequence.length - 1)))
    playbackTimerRef.current = setInterval(() => {
      cursor += 1
      if (cursor >= sequence.length) {
        clearPlaybackTimer()
        setIsPlaybackRunning(false)
        return
      }
      const ts = sequence[cursor]
      setFocusedTs(ts)
      setFrozenTs(ts)
    }, intervalMs)
  }

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
          idx === focusedIndex
            ? '#f59e0b'
            : idx === hoverIndex
              ? '#a855f7'
              : selectedMetricType === 'boolean'
                ? '#22c55e'
                : '#0ea5e9',
        ),
        pointBorderColor: chartPoints.map((_p, idx) =>
          idx === focusedIndex ? '#f59e0b' : idx === hoverIndex ? '#a855f7' : 'transparent',
        ),
        pointRadius: chartPoints.map((_p, idx) => (idx === focusedIndex || idx === hoverIndex ? 4 : 0)),
        borderWidth: 2,
        fill: true,
        tension: selectedMetricType === 'boolean' ? 0 : 0.2,
        stepped: selectedMetricType === 'boolean' ? 'before' : false,
      },
    ],
  }

  const chartOptions = {
    maintainAspectRatio: false,
    animation: false,
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
      if (suppressNextChartClickRef.current) {
        suppressNextChartClickRef.current = false
        return
      }
      stopPlayback()
      if (!elements?.length) return
      const idx = elements[0].index
      const p = chartPoints[idx]
      if (!p) return
      setHoverTs(null)
      setFocusedTs(p.ts)
      setIsLivePlaying(false)
    },
    onHover: (_event, elements) => {
      if (!elements?.length) {
        setHoverTs(null)
        return
      }
      const idx = elements[0].index
      const p = chartPoints[idx]
      setHoverTs(p?.ts || null)
    },
  }

  const beginDragSelect = (e) => {
    stopPlayback()
    const chart = chartRef.current
    if (!chart?.canvas || chartPoints.length < 2) return
    const rect = chart.canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const area = chart.chartArea
    if (!area) return
    if (x < area.left || x > area.right || y < area.top || y > area.bottom) return
    setDragSelect({ startX: x, currentX: x })
  }

  const updateDragSelect = (e) => {
    if (!dragSelect) return
    const chart = chartRef.current
    if (!chart?.canvas) return
    const rect = chart.canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    setDragSelect((prev) => (prev ? { ...prev, currentX: x } : prev))
  }

  const finishDragSelect = () => {
    if (!dragSelect) return
    const chart = chartRef.current
    const area = chart?.chartArea
    if (!chart || !area) {
      setDragSelect(null)
      return
    }

    const minX = Math.max(area.left, Math.min(dragSelect.startX, dragSelect.currentX))
    const maxX = Math.min(area.right, Math.max(dragSelect.startX, dragSelect.currentX))
    const dragWidth = maxX - minX
    setDragSelect(null)
    if (dragWidth < 8) return

    const xScale = chart.scales?.x
    if (!xScale || chartPoints.length < 2) return
    const startIndex = Math.max(0, Math.min(chartPoints.length - 1, Math.round(Number(xScale.getValueForPixel(minX)))))
    const endIndex = Math.max(0, Math.min(chartPoints.length - 1, Math.round(Number(xScale.getValueForPixel(maxX)))))
    const startTs = chartPoints[Math.min(startIndex, endIndex)]?.ts
    const endTs = chartPoints[Math.max(startIndex, endIndex)]?.ts
    if (!startTs || !endTs || startTs >= endTs) return

    const startISO = new Date(startTs).toISOString()
    const endISO = new Date(endTs).toISOString()
    setRangeStartInput(isoToLocalInputValue(startISO))
    setRangeEndInput(isoToLocalInputValue(endISO))
    setActiveRange({ kind: 'custom', preset: null, start: startISO, end: endISO })
    setIsLivePlaying(false)
    setFocusedTs(null)
    setFrozenTs(endTs)
    suppressNextChartClickRef.current = true
  }

  const activeRangeLabel =
    activeRange.kind === 'preset'
      ? PRESETS[activeRange.preset]?.label || 'Preset'
      : `${new Date(activeRange.start).toLocaleString()} to ${new Date(activeRange.end).toLocaleString()}`

  const applyPreset = (preset) => {
    stopPlayback()
    const bounds = rangeBoundsFromPreset(preset)
    setTimePreset(preset)
    setRangeStartInput(isoToLocalInputValue(bounds.start))
    setRangeEndInput(isoToLocalInputValue(bounds.end))
    setActiveRange({ kind: 'preset', preset, start: bounds.start, end: bounds.end })
  }

  const applyCustomRange = () => {
    stopPlayback()
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
                    stopPlayback()
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
                    stopPlayback()
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
                      stopPlayback()
                      setHoverTs(null)
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
              <div className="small text-body-secondary mb-2">Operational Snapshot</div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>System State</span>
                {roStatusBadge()}
              </div>
              <div className="d-flex justify-content-between align-items-center mb-3">
                <span>Backwash Lockout</span>
                {boolBadge(data.lockout, 'Active', 'Inactive')}
              </div>
              <hr className="my-2" />
              <div className="small text-body-secondary mb-2">Totalizers</div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>Total RO Flow</span>
                <span className="fw-semibold">{formatSnapshotNumber(totalROFlow)} gal</span>
              </div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>Total Feed/Inlet Flow</span>
                <span className="fw-semibold">{formatSnapshotNumber(totalFeedOrInletFlow)} gal</span>
              </div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>Total Recycle/Conc Flow</span>
                <span className="fw-semibold">{formatSnapshotNumber(totalRecycleOrConcFlow)} gal</span>
              </div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>Total Delivery Flow</span>
                <span className="fw-semibold">{formatSnapshotNumber(totalDeliveryFlow)} gal</span>
              </div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>Power Meter</span>
                <span className="fw-semibold">{formatSnapshotNumber(powerMeter)}</span>
              </div>
              <hr className="my-2" />
              <div className="small text-body-secondary mb-2">Alarm and Warning Registers</div>
              {data.alarm && (
                <div className="d-flex justify-content-between align-items-center mb-2">
                  <span>Alarm</span>
                  {boolBadge(data.alarm, 'Active', 'Clear')}
                </div>
              )}
              <div className="small text-body-secondary mt-2 mb-1">Active Warnings</div>
              <ul className="mb-0 ps-3 small">
                {registerWarnings.length === 0 && <li>No active alarm/warning bits.</li>}
                {registerWarnings.map((entry) => (
                  <li key={entry}>{entry}</li>
                ))}
              </ul>
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
              {hoverTs && !focusedTs && (
                <span className="ms-2 text-body-secondary" style={{ fontSize: '0.85rem' }}>
                  Preview at {new Date(hoverTs).toLocaleString()}
                </span>
              )}
              <CButton
                color={isPlaybackRunning ? 'warning' : 'secondary'}
                variant={isPlaybackRunning ? undefined : 'outline'}
                size="sm"
                className="ms-2"
                disabled={chartPoints.length < 2}
                onClick={() => {
                  if (isPlaybackRunning) {
                    stopPlayback()
                    return
                  }
                  startPlayback()
                }}
              >
                {isPlaybackRunning ? 'Stop Playback' : 'Playback 10s'}
              </CButton>
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
                  <div
                    style={{ height: '100%', position: 'relative' }}
                    onMouseDown={beginDragSelect}
                    onMouseMove={updateDragSelect}
                    onMouseUp={finishDragSelect}
                    onMouseLeave={finishDragSelect}
                  >
                    <CChartLine ref={chartRef} data={chartData} options={chartOptions} />
                    {dragSelect && chartRef.current?.chartArea && (
                      <div
                        style={{
                          position: 'absolute',
                          top: chartRef.current.chartArea.top,
                          height: chartRef.current.chartArea.bottom - chartRef.current.chartArea.top,
                          left: Math.max(
                            chartRef.current.chartArea.left,
                            Math.min(dragSelect.startX, dragSelect.currentX),
                          ),
                          width: Math.max(1, Math.abs(dragSelect.currentX - dragSelect.startX)),
                          background: 'rgba(14,165,233,0.18)',
                          border: '1px solid rgba(14,165,233,0.55)',
                          pointerEvents: 'none',
                        }}
                      />
                    )}
                  </div>
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
