import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import CIcon from '@coreui/icons-react'
import { cilDataTransferDown } from '@coreui/icons'
import {
  CBadge,
  CButton,
  CButtonGroup,
  CCard,
  CCardBody,
  CCardHeader,
  CCol,
  CRow,
} from '@coreui/react'
import { CChartLine } from '@coreui/react-chartjs'

import BluerockSchematic from '../../components/detailed/schematics/BluerockSchematic'
import SantaTeresaSchematic from '../../components/detailed/schematics/SantaTeresaSchematic'
import PryorFarmsSchematic from '../../components/detailed/schematics/PryorFarmsSchematic'
import { fetchStateRange } from '../../api/state'
import { subscribeLatestState } from '../../api/stateStream'
import { bitTables, decodeBitfield } from '../../utils/bitfields'
import { Key } from '../../components/detailed'
import { useHeaderContent } from '../../components/header/HeaderContentContext'
import PlaybackTimePicker from './PlaybackTimePicker'

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
  feedflow_soft: 'FTF',
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

const SITE_SENSOR_OVERRIDES = {
  bluerock: {
    runflush: { dataKey: 'flushrun' },
  },
  santateresa: {
    runflush: { dataKey: 'flushrun' },
  },
  pryorfarm: {
    runflush: { dataKey: 'flushrun' },
  },
}

const SENSOR_META = {
  permeateflow: { label: 'Permeate Flow', unit: 'GPM', type: 'number' },
  feedflow: { label: 'Feed Flow', unit: 'GPM', type: 'number' },
  feedflow_soft: { label: 'Feed Flow (Estimated)', unit: 'GPM', type: 'number' },
  deliveryflow: { label: 'Delivery Flow', unit: 'GPM', type: 'number' },
  recycleflow: { label: 'Recycle Flow', unit: 'GPM', type: 'number' },
  inletflow: { label: 'Inlet Flow', unit: 'GPM', type: 'number' },
  feedtanklevel: { label: 'Feed Tank Level', unit: '%', type: 'number' },
  prodtanklevel: { label: 'Product Tank Level', unit: '%', type: 'number' },
  residualtanklevel: { label: 'Residual Tank Level', unit: '%', type: 'number' },
  permtds: { label: 'Permeate Conductivity', unit: 'µS/cm', type: 'number' },
  feedtds: { label: 'Feed Conductivity', unit: 'µS/cm', type: 'number' },
  permnitrate: { label: 'Permeate Nitrate', unit: 'mg/L as NO3-N', type: 'number' },
  permtemp: { label: 'Permeate Temperature', unit: '°C', type: 'number' },
  inletpressure: { label: 'Inlet Pressure', unit: 'PSI', type: 'number' },
  feedpressure: { label: 'Feed Pressure', unit: 'PSI', type: 'number' },
  ropressure: { label: 'RO Pressure', unit: 'PSI', type: 'number' },
  concentratepressure: { label: 'Concentrate Pressure', unit: 'PSI', type: 'number' },
  permeatepressure: { label: 'Permeate Pressure', unit: 'PSI', type: 'number' },
  deliverypressure: { label: 'Delivery Pressure', unit: 'PSI', type: 'number' },
  state: { label: 'System State', type: 'number' },
  lockout: { label: 'Backwash Lockout', type: 'boolean' },
  totalroflow: { label: 'Total RO Flow', unit: 'gal', type: 'number' },
  totalfeedflow: { label: 'Total Feed Flow', unit: 'gal', type: 'number' },
  totalinletflow: { label: 'Total Inlet Flow', unit: 'gal', type: 'number' },
  totalrecycleflow: { label: 'Total Recycle Flow', unit: 'gal', type: 'number' },
  totalconcflow: { label: 'Total Concentrate Flow', unit: 'gal', type: 'number' },
  totaldelflow: { label: 'Total Delivery Flow', unit: 'gal', type: 'number' },
  powermeter: { label: 'Power Meter', type: 'number' },
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

function getSiteSensorOverride(siteKey, key) {
  return SITE_SENSOR_OVERRIDES[siteKey]?.[key] || null
}

function resolveMetricDataKey(siteKey, key) {
  return getSiteSensorOverride(siteKey, key)?.dataKey || key
}

function getMetricValue(row, siteKey, key) {
  if (!row || !key) return undefined
  const resolvedKey = resolveMetricDataKey(siteKey, key)
  const resolvedValue = row?.[resolvedKey]
  if (resolvedValue !== undefined) return resolvedValue
  return row?.[key]
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
  const d = new Date(ts)
  return [
    d.toLocaleDateString([], { month: '2-digit', day: '2-digit', year: '2-digit' }),
    d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  ]
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

function inferSensorType(rows, siteKey, key) {
  const configured = SENSOR_META[key]?.type
  if (configured) return configured
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    const v = getMetricValue(rows[i], siteKey, key)
    if (typeof v === 'boolean') return 'boolean'
    if (typeof v === 'number') return 'number'
  }
  return 'number'
}

function sensorDisplayName(siteKey, key) {
  if (!key) return 'Sensor'
  const override = getSiteSensorOverride(siteKey, key)
  if (override?.label) return override.label
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

function formatDataAgeLabel(lastDataAtMs) {
  if (!Number.isFinite(lastDataAtMs) || lastDataAtMs <= 0) return ''
  const ageSec = Math.max(0, Math.floor((Date.now() - lastDataAtMs) / 1000))
  if (ageSec < 1) return 'just now'
  if (ageSec < 60) return `${ageSec}s ago`
  const ageMin = Math.floor(ageSec / 60)
  if (ageMin < 60) return `${ageMin}m ago`
  const ageHour = Math.floor(ageMin / 60)
  return `${ageHour}h ago`
}

const buildLiveMd = (data = {}, siteKey, onSelectSensor = () => {}, selectedKeys = []) => {
  const selectedSet = new Set(selectedKeys)
  return {
  get: (key, field) => {
    const override = getSiteSensorOverride(siteKey, key)
    const value = getMetricValue(data, siteKey, key)
    if (field === 'abbreviated_name') {
      return override?.abbreviation || ABBR[key] || key?.slice(0, 3)?.toUpperCase() || ''
    }
    if (field === 'units') return SENSOR_META[key]?.unit || ''
    if (field === 'current_value') return value
    if (field === 'is_selected') return selectedSet.has(key)
    if (field === 'on_click') {
      if (!key || key === '???') return () => {}
      const handler = (event) => onSelectSensor(key, event)
      handler.__sensorKey = key
      handler.__isSelected = selectedSet.has(key)
      return handler
    }
    return ''
  },
  }
}

const DetailedDashboard = () => {
  const dispatch = useDispatch()
  const { setHeaderContent } = useHeaderContent()
  const selectedSystem = useSelector((state) => state.selectedSystem)
  const [timelineRows, setTimelineRows] = useState([])
  const [stateError, setStateError] = useState('')
  const [isRangeLoading, setIsRangeLoading] = useState(false)
  const [streamState, setStreamState] = useState('connecting')
  const [hasFreshData, setHasFreshData] = useState(false)
  const [lastDataAtMs, setLastDataAtMs] = useState(0)
  const [isLivePlaying, setIsLivePlaying] = useState(true)
  const [focusedTs, setFocusedTs] = useState(null)
  const [hoverTs, setHoverTs] = useState(null)
  const [hoverRow, setHoverRow] = useState(null)
  const [hoverPointIndex, setHoverPointIndex] = useState(-1)
  const [frozenTs, setFrozenTs] = useState(null)
  const [timePreset, setTimePreset] = useState('1h')
  const initialBounds = rangeBoundsFromPreset('1h')
  const [rangeStartInput, setRangeStartInput] = useState(isoToLocalInputValue(initialBounds.start))
  const [rangeEndInput, setRangeEndInput] = useState(isoToLocalInputValue(initialBounds.end))
  const [activeRange, setActiveRange] = useState({
    kind: 'preset',
    preset: '1h',
    start: initialBounds.start,
    end: initialBounds.end,
  })
  const [selectedMetricKeys, setSelectedMetricKeys] = useState([DEFAULT_METRIC_KEY])
  const [isTrendExpanded, setIsTrendExpanded] = useState(false)
  const [detailSidePanelMode, setDetailSidePanelMode] = useState('status')
  const [urlStateReady, setURLStateReady] = useState(false)
  const [dragSelect, setDragSelect] = useState(null)
  const chartRef = useRef(null)
  const schematicContainerRef = useRef(null)
  const keySvgRef = useRef(null)
  const suppressNextChartClickRef = useRef(false)
  const chartPointsRef = useRef([])
  const timelineRowsRef = useRef([])
  const pendingURLFocusTsRef = useRef(null)
  const freshDataPulseTimerRef = useRef(null)
  const freshDataPulseVisibleRef = useRef(false)

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
        setSelectedMetricKeys([parsed.metric])
      }

      pendingURLFocusTsRef.current = parsed.focusTs
      if (parsed.focusTs) {
        setIsLivePlaying(false)
      } else {
        setIsLivePlaying(parsed.live)
      }
      setFocusedTs(null)
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
    params.set('metric', selectedMetricKeys[0] || DEFAULT_METRIC_KEY)
    if (activeRange.kind === 'preset' && activeRange.preset) {
      params.set('preset', activeRange.preset)
    }
    pushHashParams(params)
  }, [urlStateReady, siteKey, isLivePlaying, activeRange, selectedMetricKeys])

  const Schematic =
    selectedSystem === 'Bluerock'
      ? BluerockSchematic
      : selectedSystem === 'Pryor Farms'
        ? PryorFarmsSchematic
        : SantaTeresaSchematic

  const latestRow = timelineRows.length ? timelineRows[timelineRows.length - 1] : null
  const activeTs = hoverTs ?? (isLivePlaying ? toTs(latestRow) : frozenTs)
  const activeRow = hoverRow || (activeTs ? nearestRow(timelineRows, activeTs) : latestRow)
  const data = activeRow || {}
  const selectedMetricKey = selectedMetricKeys[0] || DEFAULT_METRIC_KEY
  const handleSelectSensor = (key, event) => {
    if (!key || key === '???') return
    const isMulti = Boolean(event?.ctrlKey || event?.metaKey)
    if (!isMulti) {
      setSelectedMetricKeys([key])
      return
    }
    setSelectedMetricKeys((prev) => {
      const exists = prev.includes(key)
      if (exists) {
        const next = prev.filter((k) => k !== key)
        return next.length ? next : [DEFAULT_METRIC_KEY]
      }
      const next = [...prev, key]
      return next.slice(-6)
    })
  }
  const selectedMetricLabel = sensorDisplayName(siteKey, selectedMetricKey)
  const selectTrendMetric = (key) => {
    if (!key) return
    setSelectedMetricKeys([key])
  }

  const md = useMemo(
    () => buildLiveMd(data, siteKey, handleSelectSensor, selectedMetricKeys),
    [data, siteKey, selectedMetricKeys],
  )

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setIsRangeLoading(true)

    fetchStateRange(siteKey, {
      signal: controller.signal,
      start: activeRange.start,
      end: activeRange.end,
      soft: true,
    })
      .then((payload) => {
        const rows = Array.isArray(payload?.data) ? payload.data : []
        const pendingFocusTs = pendingURLFocusTsRef.current
        const focusRow = Number.isFinite(pendingFocusTs) ? nearestRow(rows, pendingFocusTs) : null
        const resolvedFocusTs = focusRow ? toTs(focusRow) : null
        setTimelineRows(rows)
        setFocusedTs(resolvedFocusTs)
        setHoverTs(null)
        setHoverRow(null)
        setHoverPointIndex(-1)
        setFrozenTs(
          resolvedFocusTs || (rows.length ? toTs(rows[rows.length - 1]) : null),
        )
        pendingURLFocusTsRef.current = null
        setStateError('')
      })
      .catch((err) => {
        if (err?.name === 'AbortError') return
        setStateError(err?.message || 'Failed to load time range')
      })
      .finally(() => {
        if (active) setIsRangeLoading(false)
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [siteKey, activeRange])

  useEffect(() => {
    let active = true
    let ws = null
    let reconnectTimer = null
    let retryDelayMs = 1000

    const openSocket = () => {
      if (!active) return
      setStreamState((prev) => (prev === 'connected' ? 'connected' : 'connecting'))
      setHasFreshData(false)
      freshDataPulseVisibleRef.current = false
      ws = subscribeLatestState(siteKey, {
        soft: true,
        onOpen: () => {
          if (!active) return
          setStreamState('connected')
        },
        onMessage: (payload) => {
          if (!active || payload?.type !== 'state.latest' || !payload?.data) return
          console.log('[ws] state.latest packet', {
            site: siteKey,
            receivedAt: new Date().toISOString(),
            rowTime: payload?.data?.plctime || payload?.data?.recordtime || null,
          })
          setTimelineRows((prev) => mergeRows(prev, [payload.data]))
          setLastDataAtMs(Date.now())
          // Pulse briefly on new data without extending indefinitely under high message rates.
          if (!freshDataPulseVisibleRef.current) {
            setHasFreshData(true)
            freshDataPulseVisibleRef.current = true
            if (freshDataPulseTimerRef.current) clearTimeout(freshDataPulseTimerRef.current)
            freshDataPulseTimerRef.current = setTimeout(() => {
              if (active) setHasFreshData(false)
              freshDataPulseVisibleRef.current = false
            }, 300)
          }
          setStateError('')
        },
      })

      ws.onclose = () => {
        if (!active) return
        setStreamState('reconnecting')
        setHasFreshData(false)
        freshDataPulseVisibleRef.current = false
        reconnectTimer = setTimeout(openSocket, retryDelayMs)
        retryDelayMs = Math.min(retryDelayMs * 2, 10000)
      }
    }

    openSocket()
    return () => {
      active = false
      setStreamState('disconnected')
      freshDataPulseVisibleRef.current = false
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (freshDataPulseTimerRef.current) clearTimeout(freshDataPulseTimerRef.current)
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
  const valveOpenBadge = (value) => {
    if (value) return <CBadge color="success">Open</CBadge>
    return <CBadge color="danger">Closed</CBadge>
  }
  const av6ModeBadge = (isFillingProductTank) => {
    if (isFillingProductTank) return <CBadge color="success">Fill Product Tank</CBadge>
    return <CBadge color="warning">Divert Product</CBadge>
  }

  const roStatusBadge = () => {
    const stateCode = Number.isInteger(data.state) ? data.state : null
    if (stateCode === 0) return <CBadge color="danger">RO Off</CBadge>
    if (stateCode === 1) return <CBadge color="danger">EStop Pressed!</CBadge>
    if (stateCode === 2) return <CBadge color="success">RO Running</CBadge>
    if (stateCode === 3) return <CBadge color="warning">RO Standby</CBadge>
    if (stateCode === 4) return <CBadge color="info">Feed Flush</CBadge>
    if (stateCode === 5) return <CBadge color="info">Permeate Flush</CBadge>
    if (stateCode === 8) return <CBadge color="info">Flushing</CBadge>
    return <CBadge color="secondary">Unknown</CBadge>
  }

  const decodedAlarmBits = decodeBitfield(Number(data.alarmword || 0), bitTables.alarm)
  const decodedWarn0Bits = decodeBitfield(Number(data.warnword0 || 0), bitTables.warning1)
  const decodedWarn1Bits = decodeBitfield(Number(data.warnword1 || 0), bitTables.warning2)
  const registerWarnings = Array.from(new Set([...decodedAlarmBits, ...decodedWarn0Bits, ...decodedWarn1Bits]))
  const activeWarningItems = stateError ? [...registerWarnings, `Data stream error: ${stateError}`] : registerWarnings
  const activeMetricKeys = selectedMetricKeys.length ? selectedMetricKeys : [DEFAULT_METRIC_KEY]
  const metricPalette = ['#0ea5e9', '#22c55e', '#f59e0b', '#a855f7', '#ef4444', '#14b8a6']
  const activeRangeStartMs = new Date(activeRange.start).getTime()
  const activeRangeEndMs = new Date(activeRange.end).getTime()
  const pausedPresetWindowMs =
    !isLivePlaying && activeRange.kind === 'preset'
      ? PRESETS[activeRange.preset || timePreset]?.ms || 0
      : 0
  const pausedPresetEndMs = pausedPresetWindowMs > 0 ? Math.max(toTs(latestRow), Date.now()) : NaN
  const pausedPresetStartMs = pausedPresetWindowMs > 0 ? pausedPresetEndMs - pausedPresetWindowMs : NaN
  const shouldRestrictChartToActiveRange =
    !isLivePlaying && Number.isFinite(activeRangeStartMs) && Number.isFinite(activeRangeEndMs)
  const chartPoints = timelineRows
    .map((row, rowIndex) => ({ ts: toTs(row), row, rowIndex }))
    .filter((p) => p.ts > 0)
    .filter((p) => {
      if (!shouldRestrictChartToActiveRange) return true
      if (pausedPresetWindowMs > 0) {
        return p.ts >= pausedPresetStartMs && p.ts <= pausedPresetEndMs
      }
      return p.ts >= activeRangeStartMs && p.ts <= activeRangeEndMs
    })
  const chartGapThresholdMs = useMemo(() => {
    if (chartPoints.length < 3) return 5 * 60 * 1000
    const deltas = []
    for (let i = 1; i < chartPoints.length; i += 1) {
      const dt = chartPoints[i].ts - chartPoints[i - 1].ts
      if (Number.isFinite(dt) && dt > 0) deltas.push(dt)
    }
    if (!deltas.length) return 5 * 60 * 1000
    deltas.sort((a, b) => a - b)
    const median = deltas[Math.floor(deltas.length / 2)] || 60000
    return Math.max(median * 5, 2 * 60 * 1000)
  }, [chartPoints])
  const chartPointToRowIndex = useMemo(
    () => new Map(chartPoints.map((point, pointIndex) => [pointIndex, point.rowIndex])),
    [chartPoints],
  )
  chartPointsRef.current = chartPoints
  timelineRowsRef.current = timelineRows
  const focusedIndex = -1
  const hoverIndex = hoverPointIndex >= 0 && hoverPointIndex < chartPoints.length ? hoverPointIndex : -1
  const hoveredPoint = hoverIndex >= 0 ? chartPoints[hoverIndex] : null
  const hoveredRowIndex = hoverIndex >= 0 ? chartPointToRowIndex.get(hoverIndex) : null
  const hasBooleanMetric = activeMetricKeys.some((key) => inferSensorType(timelineRows, siteKey, key) === 'boolean')
  const hasNumericMetric = activeMetricKeys.some((key) => inferSensorType(timelineRows, siteKey, key) !== 'boolean')

  const chartData = {
    datasets: activeMetricKeys.map((metricKey, datasetIdx) => {
      const metricType = inferSensorType(timelineRows, siteKey, metricKey)
      const unit = SENSOR_META[metricKey]?.unit || ''
      const label =
        metricType === 'boolean'
          ? `${sensorDisplayName(siteKey, metricKey)} (On/Off)`
          : `${sensorDisplayName(siteKey, metricKey)}${unit ? ` (${unit})` : ''}`
      const lineColor = metricPalette[datasetIdx % metricPalette.length]
      const fillColor = metricType === 'boolean' ? 'rgba(34,197,94,0.22)' : 'rgba(14,165,233,0.10)'
      return {
        metricKey,
        label,
        data: chartPoints.map((p) => {
          const raw = getMetricValue(p.row, siteKey, metricKey)
          return {
            x: p.ts,
            y: metricType === 'boolean' ? (raw ? 1 : 0) : Number(raw ?? 0),
          }
        }),
        borderColor: lineColor,
        backgroundColor: fillColor,
        pointHoverRadius: datasetIdx === 0 ? 6 : 4,
        pointBackgroundColor: chartPoints.map((_p, idx) =>
          idx === focusedIndex ? '#f59e0b' : idx === hoverIndex ? lineColor : lineColor,
        ),
        pointBorderColor: chartPoints.map((_p, idx) =>
          idx === focusedIndex ? '#f59e0b' : idx === hoverIndex ? lineColor : 'transparent',
        ),
        pointRadius: chartPoints.map((_p, idx) => (idx === focusedIndex || idx === hoverIndex ? 4 : 0)),
        borderWidth: 3,
        fill: datasetIdx === 0,
        tension: metricType === 'boolean' ? 0 : 0.32,
        spanGaps: chartGapThresholdMs,
        stepped: metricType === 'boolean' ? 'before' : false,
        yAxisID: metricType === 'boolean' ? 'yBool' : 'y',
      }
    }),
  }

  const chartOptions = {
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: 'index', intersect: false },
    scales: {
      x: {
        type: 'linear',
        bounds: 'data',
        grid: { color: 'rgba(120,120,120,0.15)' },
        ticks: {
          maxTicksLimit: 8,
          callback: (value) => formatTsLabel(Number(value)),
        },
        title: { display: true, text: 'Date / Time' },
      },
      y: {
        beginAtZero: hasNumericMetric,
        grid: { color: 'rgba(120,120,120,0.15)' },
        ticks: hasNumericMetric ? undefined : { display: false },
        title: {
          display: hasNumericMetric,
          text: 'Value',
        },
      },
      yBool: {
        display: hasBooleanMetric,
        position: 'right',
        beginAtZero: true,
        min: 0,
        max: 1,
        grid: { drawOnChartArea: false },
        ticks: {
          stepSize: 1,
          callback: (value) => (Number(value) >= 1 ? 'On' : 'Off'),
        },
        title: {
          display: hasBooleanMetric,
          text: 'State',
        },
      },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        mode: 'index',
        intersect: false,
        callbacks: {
          title: (items) => {
            const ts = Number(items?.[0]?.parsed?.x)
            if (!Number.isFinite(ts)) return ''
            return new Date(ts).toLocaleString()
          },
          label: (ctx) => {
            const metricKey = ctx.dataset?.metricKey || DEFAULT_METRIC_KEY
            const metricType = inferSensorType(timelineRows, metricKey)
            const label = sensorDisplayName(metricKey)
            const unit = SENSOR_META[metricKey]?.unit || ''
            if (metricType === 'boolean') return `${label}: ${Number(ctx.parsed.y) > 0 ? 'On' : 'Off'}`
            const v = Number(ctx.parsed.y)
            return `${label}: ${v.toFixed(2)}${unit ? ` ${unit}` : ''}`
          },
        },
      },
    },
    onClick: (_event, elements) => {
      if (suppressNextChartClickRef.current) {
        suppressNextChartClickRef.current = false
        return
      }
      if (!elements?.length) return
      // Click-to-focus disabled. Hover preview is the only point inspection mode.
    },
    onHover: (event, elements, chart) => {
      const resolvedElements =
        chart?.getElementsAtEventForMode?.(event, 'index', { intersect: false }, false) || elements || []
      if (!resolvedElements.length) {
        setHoverTs(null)
        setHoverRow(null)
        setHoverPointIndex(-1)
        return
      }
      const idx = resolvedElements[0].index
      const point = chartPointsRef.current[idx]
      if (!point?.row) {
        setHoverTs(null)
        setHoverRow(null)
        setHoverPointIndex(-1)
        return
      }
      setHoverPointIndex(idx)
      setHoverTs(point.ts)
      setHoverRow(point.row)
    },
  }

  const beginDragSelect = (e) => {
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
    const startValue = Number(xScale.getValueForPixel(minX))
    const endValue = Number(xScale.getValueForPixel(maxX))
    if (!Number.isFinite(startValue) || !Number.isFinite(endValue)) return
    const nearestTs = (target) => {
      let bestTs = null
      let bestDist = Number.POSITIVE_INFINITY
      for (const p of chartPoints) {
        const dist = Math.abs(p.ts - target)
        if (dist < bestDist) {
          bestDist = dist
          bestTs = p.ts
        }
      }
      return bestTs
    }
    const startTs = nearestTs(Math.min(startValue, endValue))
    const endTs = nearestTs(Math.max(startValue, endValue))
    if (!startTs || !endTs || startTs >= endTs) return

    const startISO = new Date(startTs).toISOString()
    const endISO = new Date(endTs).toISOString()
    setActiveRange({ kind: 'custom', preset: null, start: startISO, end: endISO })
    setRangeStartInput(isoToLocalInputValue(startISO))
    setRangeEndInput(isoToLocalInputValue(endISO))
    setIsLivePlaying(false)
    setFocusedTs(null)
    setHoverTs(null)
    setHoverRow(null)
    setHoverPointIndex(-1)
    setFrozenTs(endTs)
    suppressNextChartClickRef.current = true
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
    setFocusedTs(null)
    setHoverTs(null)
    setHoverRow(null)
    setHoverPointIndex(-1)
    setFrozenTs(new Date(end).getTime())
    setIsLivePlaying(false)
  }

  const handleTogglePlay = () => {
    setIsLivePlaying((prev) => {
      if (prev) {
        return false
      }
      setFocusedTs(null)
      setFrozenTs(null)
      return true
    })
  }

  const shiftActiveWindowByIntervals = (intervalDelta) => {
    const startMs = new Date(activeRange.start).getTime()
    const endMs = new Date(activeRange.end).getTime()
    if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) return

    const windowDuration = endMs - startMs
    const stepMs = intervalDelta * windowDuration
    const now = Date.now()
    let nextStart = startMs + stepMs
    let nextEnd = endMs + stepMs

    if (nextEnd > now) {
      nextEnd = now
      nextStart = now - windowDuration
    }

    setActiveRange({
      kind: 'custom',
      preset: null,
      start: new Date(nextStart).toISOString(),
      end: new Date(nextEnd).toISOString(),
    })
    setRangeStartInput(isoToLocalInputValue(new Date(nextStart).toISOString()))
    setRangeEndInput(isoToLocalInputValue(new Date(nextEnd).toISOString()))
    setFocusedTs(null)
    setHoverTs(null)
    setHoverRow(null)
    setHoverPointIndex(-1)
    setFrozenTs(nextEnd)
    setIsLivePlaying(false)
  }

  const canStepForward = new Date(activeRange.end).getTime() < Date.now() - 5000
  const headerTimePicker = useMemo(
    () => (
      <PlaybackTimePicker
        isLivePlaying={isLivePlaying}
        focusedTs={focusedTs}
        streamState={streamState}
        hasFreshData={hasFreshData}
        lastDataAtLabel={formatDataAgeLabel(lastDataAtMs)}
        activeRangeLabel={activeRangeLabel}
        activeRangeKind={activeRange.kind}
        timePreset={timePreset}
        presets={PRESETS}
        isRangeLoading={isRangeLoading}
        onSelectPreset={applyPreset}
        rangeStartInput={rangeStartInput}
        rangeEndInput={rangeEndInput}
        onRangeStartChange={setRangeStartInput}
        onRangeEndChange={setRangeEndInput}
        onApplyCustomRange={applyCustomRange}
        onTogglePlay={handleTogglePlay}
        onStepBackInterval={() => shiftActiveWindowByIntervals(-1)}
        onStepForwardInterval={() => shiftActiveWindowByIntervals(1)}
        canStepForward={canStepForward}
        embedded
        showRangeSummary={false}
      />
    ),
    [
      isLivePlaying,
      focusedTs,
      streamState,
      activeRangeLabel,
      activeRange.kind,
      timePreset,
      isRangeLoading,
      rangeStartInput,
      rangeEndInput,
      canStepForward,
    ],
  )

  useEffect(() => {
    setHeaderContent(headerTimePicker)
    return () => setHeaderContent(null)
  }, [headerTimePicker, setHeaderContent])

  const downloadSvgNode = (svgNode, filename) => {
    if (!svgNode) return
    const clone = svgNode.cloneNode(true)
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
    clone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink')
    if (!clone.getAttribute('viewBox')) {
      const width = clone.getAttribute('width') || svgNode.clientWidth || 0
      const height = clone.getAttribute('height') || svgNode.clientHeight || 0
      if (width && height) clone.setAttribute('viewBox', `0 0 ${width} ${height}`)
    }
    const serialized = new XMLSerializer().serializeToString(clone)
    const blob = new Blob([serialized], { type: 'image/svg+xml;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
  }

  const handleDownloadDashboardSvg = () => {
    const svgNode = schematicContainerRef.current?.querySelector('svg')
    downloadSvgNode(svgNode, `${siteKey}-dashboard.svg`)
  }

  const handleDownloadKeySvg = () => {
    downloadSvgNode(keySvgRef.current, `${siteKey}-key.svg`)
  }

  const liveTrendPanel = (
    <CRow className="mb-4">
      <CCol>
        <CCard>
          <CCardHeader>
            Live Trend - {selectedMetricLabel}
            {selectedMetricKeys.length > 1 && (
              <span className="ms-2 text-body-secondary" style={{ fontSize: '0.85rem' }}>
                +{selectedMetricKeys.length - 1} compared
              </span>
            )}
            {isLivePlaying && (
              <span className="ms-2 text-body-secondary" style={{ fontSize: '0.85rem' }}>
                Following latest
              </span>
            )}
            <span className="ms-2 text-body-secondary" style={{ fontSize: '0.85rem' }}>
              Ctrl/Cmd+click sensors to compare
            </span>
            {hoverTs && (
              <span className="ms-2 text-body-secondary" style={{ fontSize: '0.85rem' }}>
                Preview at {new Date(hoverTs).toLocaleString()}
              </span>
            )}
            <CButton
              color="secondary"
              variant="outline"
              size="sm"
              className="ms-2"
              onClick={() => setIsTrendExpanded((prev) => !prev)}
            >
              {isTrendExpanded ? 'Compact Trend' : 'Expand Trend'}
            </CButton>
          </CCardHeader>
          <CCardBody>
            <div style={{ height: isTrendExpanded ? 320 : 128 }}>
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
                  <CChartLine ref={chartRef} data={chartData} options={chartOptions} style={{ height: '100%' }} />
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
            <details className="mt-2">
              <summary className="small text-body-secondary" style={{ cursor: 'pointer' }}>
                Hover Debug
              </summary>
              <pre
                className="small mt-2 mb-0 p-2 border rounded bg-body-tertiary"
                style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
              >
                {JSON.stringify(
                  {
                    siteKey,
                    isLivePlaying,
                    streamState,
                    activeRange,
                    selectedMetricKeys,
                    hoverPointIndex,
                    hoverIndex,
                    hoveredRowIndex,
                    hoverTs,
                    hoverTsISO: hoverTs ? new Date(hoverTs).toISOString() : null,
                    hoveredPointTs: hoveredPoint?.ts ?? null,
                    hoveredPointTsISO: hoveredPoint?.ts ? new Date(hoveredPoint.ts).toISOString() : null,
                    hoveredPointRowIndex: hoveredPoint?.rowIndex ?? null,
                    hoverRowTs: hoverRow ? toTs(hoverRow) : null,
                    hoverRowTsISO: hoverRow ? new Date(toTs(hoverRow)).toISOString() : null,
                    activeTs,
                    activeTsISO: activeTs ? new Date(activeTs).toISOString() : null,
                    latestRowTs: latestRow ? toTs(latestRow) : null,
                    latestRowTsISO: latestRow ? new Date(toTs(latestRow)).toISOString() : null,
                    frozenTs,
                    frozenTsISO: frozenTs ? new Date(frozenTs).toISOString() : null,
                    chartPointsCount: chartPoints.length,
                    timelineRowsCount: timelineRows.length,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </CCardBody>
        </CCard>
      </CCol>
    </CRow>
  )

  return (
    <>
      <CRow className="mb-3">
        <CCol lg={8} className="mb-4 mb-lg-0">
          <CCard className="detailed-schematic-card">
            <CCardHeader className="d-flex justify-content-between align-items-center gap-2 flex-wrap">
              <span>Detailed Process Flow</span>
              <CButton color="secondary" variant="outline" size="sm" onClick={handleDownloadDashboardSvg}>
                <CIcon icon={cilDataTransferDown} size="sm" className="me-1" />
                Download SVG
              </CButton>
            </CCardHeader>
            <CCardBody className="detailed-schematic-body">
              <div ref={schematicContainerRef} className="w-100" style={{ height: 420 }}>
                <Schematic md={md} />
              </div>
            </CCardBody>
          </CCard>
        </CCol>
        <CCol lg={4}>
          <CCard>
            <CCardHeader className="d-flex justify-content-between align-items-center gap-2 flex-wrap">
              <span>{detailSidePanelMode === 'status' ? 'Sensor Status' : 'Component Key'}</span>
              <div className="d-flex align-items-center gap-2 flex-wrap">
                <CButton color="secondary" variant="outline" size="sm" onClick={handleDownloadKeySvg}>
                  <CIcon icon={cilDataTransferDown} size="sm" className="me-1" />
                  Download SVG
                </CButton>
                <CButtonGroup size="sm" aria-label="Detailed dashboard side panel">
                  <CButton
                    color={detailSidePanelMode === 'status' ? 'primary' : 'secondary'}
                    variant={detailSidePanelMode === 'status' ? undefined : 'outline'}
                    onClick={() => setDetailSidePanelMode('status')}
                  >
                    Status
                  </CButton>
                  <CButton
                    color={detailSidePanelMode === 'key' ? 'primary' : 'secondary'}
                    variant={detailSidePanelMode === 'key' ? undefined : 'outline'}
                    onClick={() => setDetailSidePanelMode('key')}
                  >
                    Key
                  </CButton>
                </CButtonGroup>
              </div>
            </CCardHeader>
            <CCardBody className="sensor-status-card-body sensor-status-panel-body">
              {detailSidePanelMode === 'key' ? (
                <div className="schematic-key-panel">
                  <svg
                    ref={keySvgRef}
                    width="100%"
                    height="100%"
                    viewBox="0 0 400 500"
                    preserveAspectRatio="xMidYMid meet"
                    role="img"
                    aria-label="Detailed schematic key"
                  >
                    <Key />
                  </svg>
                </div>
              ) : (
                <>
                  <div className="small text-body-secondary mb-2">Operational Snapshot</div>
                  <div
                    className="d-flex justify-content-between align-items-center mb-2"
                    style={{ cursor: 'pointer' }}
                    onClick={() => selectTrendMetric('state')}
                  >
                    <span>System State</span>
                    {roStatusBadge()}
                  </div>
                  <div
                    className="d-flex justify-content-between align-items-center mb-3"
                    style={{ cursor: 'pointer' }}
                    onClick={() => selectTrendMetric('lockout')}
                  >
                    <span>Backwash Lockout</span>
                    {boolBadge(data.lockout, 'Active', 'Inactive')}
                  </div>
                  <hr className="my-2" />
                  <div className="small text-body-secondary mb-2">Key Sensors</div>
                  <div
                    className="d-flex justify-content-between align-items-center mb-2"
                    style={{ cursor: 'pointer' }}
                    onClick={() => selectTrendMetric('wellpumprun')}
                  >
                    <span>Well Pump</span>
                    {boolBadge(data.wellpumprun)}
                  </div>
                  <div
                    className="d-flex justify-content-between align-items-center mb-2"
                    style={{ cursor: 'pointer' }}
                    onClick={() => selectTrendMetric('feedpumprun')}
                  >
                    <span>P1 Feed Pump</span>
                    {boolBadge(data.feedpumprun)}
                  </div>
                  <div
                    className="d-flex justify-content-between align-items-center mb-2"
                    style={{ cursor: 'pointer' }}
                    onClick={() => selectTrendMetric('inletrun')}
                  >
                    <span>AV1 Inlet Valve</span>
                    {valveOpenBadge(data.inletrun)}
                  </div>
                  <div
                    className="d-flex justify-content-between align-items-center mb-2"
                    style={{ cursor: 'pointer' }}
                    onClick={() => selectTrendMetric('ropumprun')}
                  >
                    <span>P2 RO Pump</span>
                    {boolBadge(data.ropumprun)}
                  </div>
                  <div
                    className="d-flex justify-content-between align-items-center mb-2"
                    style={{ cursor: 'pointer' }}
                    onClick={() => selectTrendMetric('proddiversionrun')}
                  >
                    <span>AV6 Product Diversion Valve</span>
                    {av6ModeBadge(data.proddiversionrun)}
                  </div>
                  <div
                    className="d-flex justify-content-between align-items-center mb-2"
                    style={{ cursor: 'pointer' }}
                    onClick={() => selectTrendMetric('deliveryrun')}
                  >
                    <span>P3 Delivery Pump</span>
                    {boolBadge(data.deliveryrun)}
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
                    {activeWarningItems.length === 0 && <li>No active alarm/warning bits.</li>}
                    {activeWarningItems.map((entry) => (
                      <li key={entry}>{entry}</li>
                    ))}
                  </ul>
                </>
              )}
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>
      {liveTrendPanel}

    </>
  )
}

export default DetailedDashboard
