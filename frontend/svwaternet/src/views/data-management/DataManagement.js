import React, { useEffect, useMemo, useState } from 'react'
import { useSelector } from 'react-redux'
import ReactECharts from 'echarts-for-react'
import {
  CAlert,
  CBadge,
  CButton,
  CCard,
  CCardBody,
  CCardHeader,
  CCol,
  CFormInput,
  CFormLabel,
  CFormSelect,
  CFormSwitch,
  CFormTextarea,
  CRow,
  CSpinner,
  CTable,
  CTableBody,
  CTableDataCell,
  CTableHead,
  CTableHeaderCell,
  CTableRow,
} from '@coreui/react'
import { apiPost } from '../../api/client'

const SITE_BY_SYSTEM = {
  Bluerock: 'bluerock',
  'Santa Teresa': 'santateresa',
  'Pryor Farms': 'pryorfarm',
}

const MAX_PREVIEW_ROWS = 100

function defaultQueryJSON() {
  const end = new Date()
  const start = new Date(end.getTime() - 24 * 60 * 60 * 1000)
  return JSON.stringify(
    {
      time_window: {
        start: start.toISOString(),
        end: end.toISOString(),
      },
      match: 'all',
      conditions: [{ field: 'state', op: 'eq', value: 2 }],
      max_results: 50000,
      include_rows: true,
    },
    null,
    2,
  )
}

function toLocalDateTimeInputValue(date) {
  const d = new Date(date)
  if (Number.isNaN(d.getTime())) return ''
  const offsetMs = d.getTimezoneOffset() * 60 * 1000
  return new Date(d.getTime() - offsetMs).toISOString().slice(0, 16)
}

function fromLocalDateTimeInputValue(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return d.toISOString()
}

function csvEscape(value) {
  const s = value == null ? '' : String(value)
  if (!/[",\n]/.test(s)) return s
  return `"${s.replaceAll('"', '""')}"`
}

function rowsToCSV(rows) {
  if (!rows.length) return ''
  const seen = new Set()
  const columns = []
  const priority = ['plctime', 'recordtime', 'id', 'state', 'alarmword', 'warnword0', 'warnword1']
  for (const key of priority) {
    if (rows.some((row) => Object.hasOwn(row, key))) {
      seen.add(key)
      columns.push(key)
    }
  }
  for (const row of rows) {
    for (const key of Object.keys(row || {})) {
      if (!seen.has(key)) {
        seen.add(key)
        columns.push(key)
      }
    }
  }
  const lines = [columns.join(',')]
  for (const row of rows) {
    lines.push(columns.map((key) => csvEscape(row?.[key])).join(','))
  }
  return `${lines.join('\n')}\n`
}

function downloadTextFile(filename, text, mimeType = 'text/plain;charset=utf-8') {
  const blob = new Blob([text], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function inferColumns(rows) {
  const priority = ['plctime', 'recordtime', 'state', 'alarmword', 'warnword0', 'warnword1']
  const seen = new Set()
  const columns = []
  for (const key of priority) {
    if (rows.some((row) => Object.hasOwn(row, key))) {
      columns.push(key)
      seen.add(key)
    }
  }
  for (const row of rows) {
    for (const key of Object.keys(row || {})) {
      if (!seen.has(key)) {
        columns.push(key)
        seen.add(key)
      }
    }
  }
  return columns
}

function dashboardJumpHref(site, timestamp) {
  const ts = new Date(timestamp)
  if (Number.isNaN(ts.getTime())) return '#/detailed-dashboard'
  const end = ts.toISOString()
  const start = new Date(ts.getTime() - 30 * 60 * 1000).toISOString()
  const params = new URLSearchParams({
    site,
    live: '0',
    start,
    end,
    focus: end,
  })
  return `#/detailed-dashboard?${params.toString()}`
}

function rowTimestamp(row) {
  return row?.plctime || row?.recordtime || ''
}

function toFiniteNumber(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'boolean') return value ? 1 : 0
  if (typeof value === 'string') {
    const n = Number(value.trim())
    return Number.isFinite(n) ? n : null
  }
  return null
}

function inferGapThresholdMs(rows) {
  const times = rows
    .map((row) => new Date(rowTimestamp(row)).getTime())
    .filter((ts) => Number.isFinite(ts))
  if (times.length < 3) return Number.POSITIVE_INFINITY
  const diffs = []
  for (let i = 1; i < times.length; i += 1) {
    const d = times[i] - times[i - 1]
    if (d > 0) diffs.push(d)
  }
  if (!diffs.length) return Number.POSITIVE_INFINITY
  diffs.sort((a, b) => a - b)
  const median = diffs[Math.floor(diffs.length / 2)]
  return Math.max(median * 4, 60 * 1000)
}

function buildGapAwareSeriesPoints(rows, field, gapThresholdMs) {
  const points = []
  let prevTs = null
  for (const row of rows) {
    const ts = new Date(rowTimestamp(row)).getTime()
    if (!Number.isFinite(ts)) continue

    if (prevTs != null && Number.isFinite(gapThresholdMs) && ts - prevTs > gapThresholdMs) {
      // Insert a null point to force a visual break across sparse periods.
      points.push([prevTs + 1, null])
    }

    const value = toFiniteNumber(row[field])
    points.push([ts, value == null ? null : value])
    prevTs = ts
  }
  return points
}

const CHART_COLORS = ['#58a6ff', '#3fb950', '#f2cc60', '#ff7b72', '#bc8cff', '#56d4dd']
const ACTIONS_COL_WIDTH = 190
const PLCTIME_COL_WIDTH = 220
const DEFAULT_VISIBLE_COLUMN_KEYS = [
  'state',
  'ropumprun',
  'feedtanklevel',
  'prodtanklevel',
  'permeateflow',
  'concentrateflow',
]

function normalizeColumnKey(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '')
}

function pickDefaultVisibleColumns(columns) {
  const available = columns.filter((col) => col !== 'plctime')
  const keyToColumn = new Map()
  for (const col of available) {
    keyToColumn.set(normalizeColumnKey(col), col)
  }
  const picks = []
  const seen = new Set()
  const candidatesByKey = {
    state: ['state'],
    ropumprun: ['ropumprun'],
    feedtanklevel: ['feedtanklevel', 'feedtankdepth'],
    prodtanklevel: ['prodtanklevel', 'prodtankdepth'],
    permeateflow: ['permeateflow', 'permeatefow'],
    concentrateflow: ['concentrateflow', 'concentraetflow'],
  }

  for (const defaultKey of DEFAULT_VISIBLE_COLUMN_KEYS) {
    const candidates = candidatesByKey[defaultKey] || [defaultKey]
    for (const candidate of candidates) {
      const hit = keyToColumn.get(normalizeColumnKey(candidate))
      if (hit && !seen.has(hit)) {
        picks.push(hit)
        seen.add(hit)
        break
      }
    }
  }

  if (picks.length) return picks
  return available.slice(0, Math.min(8, available.length))
}

const DataManagement = () => {
  const selectedSystem = useSelector((state) => state.selectedSystem)
  const siteKey = SITE_BY_SYSTEM[selectedSystem] || 'bluerock'

  const [queryText, setQueryText] = useState(defaultQueryJSON)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showAdvancedQuery, setShowAdvancedQuery] = useState(false)
  const [timestamps, setTimestamps] = useState([])
  const [matchedRows, setMatchedRows] = useState([])
  const [stackedYAxis, setStackedYAxis] = useState([])
  const [visibleColumns, setVisibleColumns] = useState([])
  const [lastMeta, setLastMeta] = useState(null)

  const previewRows = useMemo(() => matchedRows.slice(0, MAX_PREVIEW_ROWS), [matchedRows])
  const tableColumns = useMemo(
    () => inferColumns(matchedRows).filter((col) => col !== 'recordtime'),
    [matchedRows],
  )
  useEffect(() => {
    const available = tableColumns.filter((col) => col !== 'plctime')
    if (!available.length) {
      setVisibleColumns([])
      return
    }
    setVisibleColumns((prev) => {
      const kept = prev.filter((col) => available.includes(col))
      if (kept.length) return kept
      return pickDefaultVisibleColumns(tableColumns)
    })
  }, [tableColumns])

  const displayedColumns = useMemo(() => {
    const out = []
    if (tableColumns.includes('plctime')) out.push('plctime')
    const picked = new Set(visibleColumns)
    for (const col of tableColumns) {
      if (col === 'plctime') continue
      if (picked.has(col)) out.push(col)
    }
    return out
  }, [tableColumns, visibleColumns])
  const numericColumns = useMemo(() => {
    const blocked = new Set(['id', 'location', 'plctime', 'recordtime'])
    const keys = []
    const seen = new Set()
    for (const row of matchedRows) {
      for (const [key, value] of Object.entries(row || {})) {
        if (blocked.has(key) || seen.has(key)) continue
        if (toFiniteNumber(value) == null) continue
        seen.add(key)
        keys.push(key)
      }
    }
    return keys
  }, [matchedRows])
  useEffect(() => {
    if (!numericColumns.length) {
      setStackedYAxis([])
      return
    }
    setStackedYAxis((prev) => prev.filter((field) => numericColumns.includes(field)))
  }, [numericColumns])

  const toggleSeriesFromColumn = (column) => {
    if (!numericColumns.includes(column)) return
    setStackedYAxis((prev) =>
      prev.includes(column) ? prev.filter((v) => v !== column) : [...prev, column],
    )
  }

  const echartOption = useMemo(() => {
    const gapThresholdMs = inferGapThresholdMs(matchedRows)
    return {
      animation: false,
      grid: {
        left: 52,
        right: 20,
        top: 42,
        bottom: 74,
      },
      legend: {
        top: 4,
        textStyle: {
          color: '#cfd7e6',
        },
      },
      tooltip: {
        trigger: 'axis',
        confine: true,
        backgroundColor: 'rgba(18, 22, 30, 0.95)',
        borderColor: 'rgba(255,255,255,0.15)',
        textStyle: {
          color: '#e7eefb',
        },
      },
      xAxis: {
        type: 'time',
        axisLabel: {
          color: '#aeb7c4',
          rotate: 35,
          hideOverlap: true,
          formatter: (value) => {
            const d = new Date(value)
            if (Number.isNaN(d.getTime())) return ''
            return d.toISOString().slice(11, 19)
          },
        },
        axisLine: {
          lineStyle: {
            color: 'rgba(255,255,255,0.18)',
          },
        },
        splitLine: {
          lineStyle: {
            color: 'rgba(255,255,255,0.08)',
          },
        },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: {
          color: '#aeb7c4',
        },
        axisLine: {
          lineStyle: {
            color: 'rgba(255,255,255,0.18)',
          },
        },
        splitLine: {
          lineStyle: {
            color: 'rgba(255,255,255,0.08)',
          },
        },
      },
      dataZoom: [
        {
          type: 'inside',
          xAxisIndex: 0,
          filterMode: 'none',
          start: 80,
          end: 100,
        },
        {
          type: 'slider',
          xAxisIndex: 0,
          filterMode: 'none',
          height: 22,
          bottom: 12,
          start: 80,
          end: 100,
          backgroundColor: 'rgba(255,255,255,0.04)',
          fillerColor: 'rgba(88, 166, 255, 0.20)',
          borderColor: 'rgba(255,255,255,0.15)',
          handleStyle: {
            color: '#58a6ff',
            borderColor: '#58a6ff',
          },
          dataBackground: {
            lineStyle: { color: 'rgba(172, 193, 224, 0.75)' },
            areaStyle: { color: 'rgba(172, 193, 224, 0.18)' },
          },
        },
      ],
      series: stackedYAxis.map((field, datasetIndex) => {
        const color = CHART_COLORS[datasetIndex % CHART_COLORS.length]
        return {
          name: field,
          type: 'line',
          smooth: false,
          showSymbol: false,
          connectNulls: false,
          lineStyle: { width: 2, color },
          itemStyle: { color },
          emphasis: { focus: 'series' },
          data: buildGapAwareSeriesPoints(matchedRows, field, gapThresholdMs),
        }
      }),
      useUTC: true,
    }
  }, [matchedRows, stackedYAxis])
  const hasPlottableSeries = useMemo(
    () =>
      stackedYAxis.some((field) =>
        matchedRows.some((row) => {
          const ts = new Date(rowTimestamp(row)).getTime()
          return Number.isFinite(ts) && toFiniteNumber(row[field]) != null
        }),
      ),
    [matchedRows, stackedYAxis],
  )

  const parsedQuery = useMemo(() => {
    try {
      const parsed = JSON.parse(queryText)
      return typeof parsed === 'object' && parsed ? parsed : null
    } catch {
      return null
    }
  }, [queryText])

  const timeWindowStart = parsedQuery?.time_window?.start
    ? new Date(parsedQuery.time_window.start)
    : null
  const timeWindowEnd = parsedQuery?.time_window?.end ? new Date(parsedQuery.time_window.end) : null

  const updateQueryTimeWindow = (nextStart, nextEnd) => {
    let parsed
    try {
      parsed = JSON.parse(queryText)
    } catch {
      setError('Fix JSON first before editing the time window fields.')
      return
    }
    const next = {
      ...parsed,
      time_window: {
        ...(parsed?.time_window || {}),
        ...(nextStart ? { start: nextStart } : {}),
        ...(nextEnd ? { end: nextEnd } : {}),
      },
    }
    setQueryText(JSON.stringify(next, null, 2))
    setError('')
  }

  const runQuery = async () => {
    setLoading(true)
    setError('')
    setTimestamps([])
    setMatchedRows([])
    setLastMeta(null)
    try {
      const req = JSON.parse(queryText)
      const payload = await apiPost(
        `/api/v1/sites/${encodeURIComponent(siteKey)}/events/query`,
        req,
      )
      const tsList = Array.isArray(payload?.timestamps) ? payload.timestamps : []
      setTimestamps(tsList)

      const startISO = req?.time_window?.start
      const endISO = req?.time_window?.end
      if (!startISO || !endISO) {
        throw new Error('Query JSON must include time_window.start and time_window.end')
      }

      const backendRows = Array.isArray(payload?.rows) ? payload.rows : null
      if (backendRows) {
        setMatchedRows(backendRows)
        setLastMeta({
          rangeStart: startISO,
          rangeEnd: endISO,
          timestampsReturned: tsList.length,
          rowsFetched: backendRows.length,
          rowsMatched: backendRows.length,
          matchedOnBackend: true,
        })
        return
      }

      if (!tsList.length) {
        setLastMeta({
          rangeStart: startISO,
          rangeEnd: endISO,
          timestampsReturned: 0,
          rowsFetched: 0,
          rowsMatched: 0,
          matchedOnBackend: false,
        })
        return
      }
      // Fallback for older backend responses that return only timestamps.
      setMatchedRows([])
      setLastMeta({
        rangeStart: startISO,
        rangeEnd: endISO,
        timestampsReturned: tsList.length,
        rowsFetched: 0,
        rowsMatched: 0,
        matchedOnBackend: false,
      })
    } catch (err) {
      setError(err?.message || 'Failed to run data query')
    } finally {
      setLoading(false)
    }
  }

  const handleDownloadCSV = () => {
    if (!matchedRows.length) return
    const csv = rowsToCSV(matchedRows)
    const stamp = new Date().toISOString().replaceAll(':', '-')
    downloadTextFile(`${siteKey}-query-results-${stamp}.csv`, csv, 'text/csv;charset=utf-8')
  }

  return (
    <CRow className="g-4">
      <CCol xs={12}>
        <CCard>
          <CCardHeader>Data Management</CCardHeader>
          <CCardBody>
            <div className="text-body-secondary mb-3">
              Run the existing events query JSON for <strong>{selectedSystem || 'Bluerock'}</strong>{' '}
              , then preview matching rows and export them as CSV.
            </div>
            <CRow className="g-3">
              <CCol md={6}>
                <CFormLabel htmlFor="dm-query-start">Time Window Start</CFormLabel>
                <CFormInput
                  id="dm-query-start"
                  type="datetime-local"
                  value={toLocalDateTimeInputValue(timeWindowStart || new Date())}
                  onChange={(e) => {
                    const iso = fromLocalDateTimeInputValue(e.target.value)
                    if (iso) updateQueryTimeWindow(iso, '')
                  }}
                />
              </CCol>
              <CCol md={6}>
                <CFormLabel htmlFor="dm-query-end">Time Window End</CFormLabel>
                <CFormInput
                  id="dm-query-end"
                  type="datetime-local"
                  value={toLocalDateTimeInputValue(timeWindowEnd || new Date())}
                  onChange={(e) => {
                    const iso = fromLocalDateTimeInputValue(e.target.value)
                    if (iso) updateQueryTimeWindow('', iso)
                  }}
                />
              </CCol>
              <CCol xs={12}>
                <CFormSwitch
                  id="dm-show-advanced"
                  label="Advanced Query"
                  checked={showAdvancedQuery}
                  onChange={(e) => setShowAdvancedQuery(e.target.checked)}
                />
              </CCol>
              {showAdvancedQuery && (
                <CCol xs={12}>
                  <CFormLabel htmlFor="dm-query-json">
                    Query JSON (existing events query language)
                  </CFormLabel>
                  <CFormTextarea
                    id="dm-query-json"
                    rows={14}
                    value={queryText}
                    onChange={(e) => setQueryText(e.target.value)}
                    spellCheck={false}
                    style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}
                  />
                </CCol>
              )}
              <CCol xs={12} className="d-flex gap-2 flex-wrap">
                <CButton color="primary" onClick={runQuery} disabled={loading}>
                  {loading ? (
                    <>
                      <CSpinner component="span" size="sm" className="me-2" />
                      Running Query
                    </>
                  ) : (
                    'Run Query'
                  )}
                </CButton>
                <CButton
                  color="secondary"
                  variant="outline"
                  onClick={() => {
                    setQueryText(defaultQueryJSON())
                    setError('')
                  }}
                  disabled={loading}
                >
                  Reset Example
                </CButton>
                <CButton
                  color="success"
                  variant="outline"
                  onClick={handleDownloadCSV}
                  disabled={loading || matchedRows.length === 0}
                >
                  Download Matching Rows (CSV)
                </CButton>
              </CCol>
            </CRow>
            {error && (
              <CAlert color="danger" className="mt-3 mb-0">
                {error}
              </CAlert>
            )}
          </CCardBody>
        </CCard>
      </CCol>

      <CCol xs={12}>
        <CCard>
          <CCardHeader>Query Results</CCardHeader>
          <CCardBody>
            <div className="d-flex flex-wrap gap-2 mb-3">
              <CBadge color="secondary">Site: {siteKey}</CBadge>
              <CBadge color="info">Timestamps: {timestamps.length}</CBadge>
              <CBadge color="success">Matched Rows: {matchedRows.length}</CBadge>
              {lastMeta?.rowsFetched != null && (
                <CBadge color="warning">
                  {lastMeta?.matchedOnBackend ? 'Returned Rows' : 'Returned Rows'}:{' '}
                  {lastMeta.rowsFetched}
                </CBadge>
              )}
            </div>
            {lastMeta?.rangeStart && (
              <div className="text-body-secondary mb-3" style={{ fontSize: '0.9rem' }}>
                Range: {new Date(lastMeta.rangeStart).toLocaleString()} to{' '}
                {new Date(lastMeta.rangeEnd).toLocaleString()}
              </div>
            )}
            <CCard className="mb-3">
              <CCardBody>
                <div className="d-flex gap-2">
                  <CBadge color="dark">Stacked Series: {stackedYAxis.length}</CBadge>
                  <CButton
                    color="secondary"
                    variant="outline"
                    size="sm"
                    disabled={!stackedYAxis.length}
                    onClick={() => setStackedYAxis([])}
                  >
                    Clear Selection
                  </CButton>
                </div>
                <div className="mt-3">
                  {!numericColumns.length ? (
                    <div className="text-body-secondary">
                      No numeric columns found for charting in this result set.
                    </div>
                  ) : (
                    <>
                      <div className="text-body-secondary mb-3" style={{ fontSize: '0.9rem' }}>
                        Click a numeric column header in the table below to add/remove it from the
                        chart.
                      </div>
                      <div className="d-flex flex-wrap gap-2 mb-3">
                        {stackedYAxis.map((field) => (
                          <CBadge color="info" key={field}>
                            {field}
                          </CBadge>
                        ))}
                      </div>
                      {!stackedYAxis.length ? (
                        <div className="text-body-secondary">Select a y-axis column to plot.</div>
                      ) : !hasPlottableSeries ? (
                        <div className="text-body-secondary">
                          Selected series have no numeric datapoints in the current rows.
                        </div>
                      ) : (
                        <div style={{ height: 340 }}>
                          <ReactECharts
                            option={echartOption}
                            style={{ height: '100%', width: '100%' }}
                            notMerge
                            lazyUpdate
                            opts={{ renderer: 'canvas' }}
                          />
                        </div>
                      )}
                    </>
                  )}
                </div>
              </CCardBody>
            </CCard>
            {!matchedRows.length ? (
              <div className="text-body-secondary">
                {timestamps.length
                  ? lastMeta?.matchedOnBackend === false
                    ? 'Backend returned timestamps only. Update the server to the latest version to return matching rows directly.'
                    : 'No matching rows returned for this query.'
                  : 'Run a query to load matching timestamps and rows.'}
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <div className="mb-3 d-flex flex-wrap gap-2 align-items-end">
                  <div style={{ minWidth: 280, maxWidth: 520 }}>
                    <CFormLabel htmlFor="dm-visible-columns">Visible Columns</CFormLabel>
                    <CFormSelect
                      id="dm-visible-columns"
                      multiple
                      size={Math.min(10, Math.max(6, tableColumns.length))}
                      value={visibleColumns}
                      onChange={(e) => {
                        const values = Array.from(e.target.selectedOptions).map((o) => o.value)
                        setVisibleColumns(values)
                      }}
                    >
                      {tableColumns
                        .filter((col) => col !== 'plctime')
                        .map((col) => (
                          <option key={col} value={col}>
                            {col}
                          </option>
                        ))}
                    </CFormSelect>
                  </div>
                  <CButton
                    color="secondary"
                    variant="outline"
                    onClick={() =>
                      setVisibleColumns(tableColumns.filter((col) => col !== 'plctime'))
                    }
                  >
                    Show All
                  </CButton>
                  <CButton
                    color="secondary"
                    variant="outline"
                    onClick={() => setVisibleColumns(pickDefaultVisibleColumns(tableColumns))}
                  >
                    Reset Default
                  </CButton>
                </div>
                <CTable hover small align="middle" style={{ minWidth: 1400 }}>
                  <CTableHead>
                    <CTableRow>
                      <CTableHeaderCell
                        scope="col"
                        style={{
                          position: 'sticky',
                          left: 0,
                          zIndex: 4,
                          minWidth: ACTIONS_COL_WIDTH,
                          width: ACTIONS_COL_WIDTH,
                          background: 'var(--cui-body-bg)',
                        }}
                      >
                        Actions
                      </CTableHeaderCell>
                      {displayedColumns.map((col) => (
                        <CTableHeaderCell
                          scope="col"
                          key={col}
                          onClick={() => toggleSeriesFromColumn(col)}
                          style={{
                            position: col === 'plctime' ? 'sticky' : 'static',
                            left: col === 'plctime' ? ACTIONS_COL_WIDTH : undefined,
                            zIndex: col === 'plctime' ? 4 : 1,
                            minWidth: col === 'plctime' ? PLCTIME_COL_WIDTH : 150,
                            width: col === 'plctime' ? PLCTIME_COL_WIDTH : undefined,
                            background: 'var(--cui-body-bg)',
                            cursor: numericColumns.includes(col) ? 'pointer' : 'default',
                            color: stackedYAxis.includes(col) ? '#58a6ff' : undefined,
                          }}
                          title={
                            numericColumns.includes(col)
                              ? stackedYAxis.includes(col)
                                ? 'Click to remove series from chart'
                                : 'Click to add series to chart'
                              : undefined
                          }
                        >
                          {col}
                          {stackedYAxis.includes(col) ? ' *' : ''}
                        </CTableHeaderCell>
                      ))}
                    </CTableRow>
                  </CTableHead>
                  <CTableBody>
                    {previewRows.map((row, idx) => {
                      const ts = rowTimestamp(row)
                      return (
                        <CTableRow key={`${ts || 'row'}-${idx}`}>
                          <CTableDataCell
                            style={{
                              whiteSpace: 'nowrap',
                              position: 'sticky',
                              left: 0,
                              zIndex: 3,
                              minWidth: ACTIONS_COL_WIDTH,
                              width: ACTIONS_COL_WIDTH,
                              background: 'var(--cui-body-bg)',
                            }}
                          >
                            <a href={dashboardJumpHref(siteKey, ts)}>Open in Dashboard</a>
                          </CTableDataCell>
                          {displayedColumns.map((col) => (
                            <CTableDataCell
                              key={col}
                              style={{
                                position: col === 'plctime' ? 'sticky' : 'static',
                                left: col === 'plctime' ? ACTIONS_COL_WIDTH : undefined,
                                zIndex: col === 'plctime' ? 3 : 1,
                                minWidth: col === 'plctime' ? PLCTIME_COL_WIDTH : 150,
                                width: col === 'plctime' ? PLCTIME_COL_WIDTH : undefined,
                                background: 'var(--cui-body-bg)',
                                maxWidth: 220,
                                whiteSpace: 'nowrap',
                                textOverflow: 'ellipsis',
                                overflow: 'hidden',
                              }}
                              title={row?.[col] == null ? '' : String(row[col])}
                            >
                              {typeof row?.[col] === 'boolean'
                                ? row[col]
                                  ? 'true'
                                  : 'false'
                                : row?.[col] == null
                                  ? ''
                                  : String(row[col])}
                            </CTableDataCell>
                          ))}
                        </CTableRow>
                      )
                    })}
                  </CTableBody>
                </CTable>
                {matchedRows.length > MAX_PREVIEW_ROWS && (
                  <div className="text-body-secondary" style={{ fontSize: '0.9rem' }}>
                    Showing first {MAX_PREVIEW_ROWS.toLocaleString()} of{' '}
                    {matchedRows.length.toLocaleString()} matched rows. CSV download includes all
                    matched rows.
                  </div>
                )}
              </div>
            )}
          </CCardBody>
        </CCard>
      </CCol>
    </CRow>
  )
}

export default DataManagement
