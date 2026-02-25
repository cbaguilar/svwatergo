import React, { useMemo, useState } from 'react'
import { useSelector } from 'react-redux'
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
      max_results: 200,
      min_gap_seconds: 60,
      include_rows: true,
    },
    null,
    2,
  )
}

function parseTsSecond(value) {
  const t = new Date(value).getTime()
  return Number.isFinite(t) ? Math.floor(t / 1000) : NaN
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
      if (columns.length >= 10) return columns
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

const DataManagement = () => {
  const selectedSystem = useSelector((state) => state.selectedSystem)
  const siteKey = SITE_BY_SYSTEM[selectedSystem] || 'bluerock'

  const [queryText, setQueryText] = useState(defaultQueryJSON)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [timestamps, setTimestamps] = useState([])
  const [matchedRows, setMatchedRows] = useState([])
  const [lastMeta, setLastMeta] = useState(null)

  const previewRows = useMemo(() => matchedRows.slice(0, MAX_PREVIEW_ROWS), [matchedRows])
  const previewColumns = useMemo(() => inferColumns(previewRows), [previewRows])

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
                <CTable hover small responsive align="middle">
                  <CTableHead>
                    <CTableRow>
                      <CTableHeaderCell scope="col">Actions</CTableHeaderCell>
                      {previewColumns.map((col) => (
                        <CTableHeaderCell scope="col" key={col}>
                          {col}
                        </CTableHeaderCell>
                      ))}
                    </CTableRow>
                  </CTableHead>
                  <CTableBody>
                    {previewRows.map((row, idx) => {
                      const ts = rowTimestamp(row)
                      return (
                        <CTableRow key={`${ts || 'row'}-${idx}`}>
                          <CTableDataCell style={{ whiteSpace: 'nowrap' }}>
                            <a href={dashboardJumpHref(siteKey, ts)}>Open in Dashboard</a>
                          </CTableDataCell>
                          {previewColumns.map((col) => (
                            <CTableDataCell
                              key={col}
                              style={{
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
