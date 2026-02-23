import React, { useEffect, useState } from 'react'
import {
  CBadge,
  CCard,
  CCardBody,
  CCardHeader,
  CTable,
  CTableBody,
  CTableDataCell,
  CTableHead,
  CTableHeaderCell,
  CTableRow,
} from '@coreui/react'
import { getMe } from '../api/auth'
import {
  createOperatorReport,
  deleteOperatorReport,
  listOperatorReports,
  updateOperatorReport,
} from '../api/reports'

const EMPTY_FORM = { title: '', body: '', status: 'open', severity: '', tags: '' }

const OperatorReportsPanel = ({ siteKey }) => {
  const [isAdmin, setIsAdmin] = useState(false)
  const [reports, setReports] = useState([])
  const [loadingReports, setLoadingReports] = useState(true)
  const [reportsError, setReportsError] = useState('')
  const [reportForm, setReportForm] = useState(EMPTY_FORM)
  const [reportSaveError, setReportSaveError] = useState('')
  const [reportSaving, setReportSaving] = useState(false)
  const [editingReportId, setEditingReportId] = useState(null)
  const [editingForm, setEditingForm] = useState(EMPTY_FORM)
  const [reportDeletingId, setReportDeletingId] = useState(null)
  const [pageSize, setPageSize] = useState(10)
  const [pageOffset, setPageOffset] = useState(0)
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [totalReports, setTotalReports] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getMe({ signal: controller.signal })
      .then((payload) => setIsAdmin(Boolean(payload?.isAdmin)))
      .catch(() => setIsAdmin(false))
    return () => controller.abort()
  }, [])

  useEffect(() => {
    setPageOffset(0)
  }, [siteKey, pageSize, searchQuery])

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setLoadingReports(true)
    setReportsError('')
    listOperatorReports(siteKey, { limit: pageSize, offset: pageOffset, q: searchQuery, signal: controller.signal })
      .then((payload) => {
        if (!active) return
        setReports(Array.isArray(payload?.reports) ? payload.reports : [])
        setTotalReports(Number(payload?.paging?.total) || 0)
      })
      .catch((err) => {
        if (!active || err?.name === 'AbortError') return
        setReports([])
        setTotalReports(0)
        setReportsError(err?.message || 'Failed to load reports')
      })
      .finally(() => {
        if (!active) return
        setLoadingReports(false)
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [siteKey, pageSize, pageOffset, searchQuery])

  const formatReportDate = (raw) => {
    if (!raw) return 'Unknown'
    const d = new Date(raw)
    if (Number.isNaN(d.getTime())) return 'Unknown'
    return d.toLocaleString()
  }

  const parseTags = (raw) =>
    raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)

  const reloadReports = async () => {
    const payload = await listOperatorReports(siteKey, { limit: pageSize, offset: pageOffset, q: searchQuery })
    setReports(Array.isArray(payload?.reports) ? payload.reports : [])
    setTotalReports(Number(payload?.paging?.total) || 0)
  }

  const startEditReport = (report) => {
    setEditingReportId(report.id)
    setEditingForm({
      title: report.title || '',
      body: report.body || '',
      status: report.status || 'open',
      severity: report.severity || '',
      tags: Array.isArray(report.tags) ? report.tags.join(', ') : '',
    })
    setReportSaveError('')
  }

  const handleCreateReport = async (e) => {
    e.preventDefault()
    setReportSaving(true)
    setReportSaveError('')
    try {
      await createOperatorReport(siteKey, {
        title: reportForm.title.trim(),
        body: reportForm.body.trim(),
        status: reportForm.status || 'open',
        severity: reportForm.severity.trim(),
        tags: parseTags(reportForm.tags),
      })
      setReportForm(EMPTY_FORM)
      await reloadReports()
    } catch (err) {
      setReportSaveError(err?.message || 'Failed to create report')
    } finally {
      setReportSaving(false)
    }
  }

  const handleUpdateReport = async (id) => {
    setReportSaving(true)
    setReportSaveError('')
    try {
      await updateOperatorReport(siteKey, id, {
        title: editingForm.title,
        body: editingForm.body,
        status: editingForm.status,
        severity: editingForm.severity,
        tags: parseTags(editingForm.tags),
      })
      setEditingReportId(null)
      await reloadReports()
    } catch (err) {
      setReportSaveError(err?.message || 'Failed to update report')
    } finally {
      setReportSaving(false)
    }
  }

  const handleDeleteReport = async (id) => {
    if (!window.confirm('Delete this report?')) return
    setReportDeletingId(id)
    setReportSaveError('')
    try {
      await deleteOperatorReport(siteKey, id)
      if (editingReportId === id) setEditingReportId(null)
      await reloadReports()
    } catch (err) {
      setReportSaveError(err?.message || 'Failed to delete report')
    } finally {
      setReportDeletingId(null)
    }
  }

  const pageStart = totalReports === 0 ? 0 : pageOffset + 1
  const pageEnd = Math.min(pageOffset + reports.length, totalReports)
  const canPrev = pageOffset > 0
  const canNext = pageOffset + pageSize < totalReports
  const currentPage = Math.floor(pageOffset / pageSize) + 1
  const totalPages = Math.max(1, Math.ceil(totalReports / pageSize))

  return (
    <CCard>
      <CCardHeader>Operator Reports</CCardHeader>
      <CCardBody>
        <div className="text-body-secondary mb-3" style={{ fontSize: '0.9rem' }}>
          Site reports are visible to all signed-in users. Create/edit/delete is restricted to admins.
        </div>
        {reportsError && <div className="text-danger mb-2">{reportsError}</div>}
        {reportSaveError && <div className="text-danger mb-2">{reportSaveError}</div>}

        {isAdmin && (
          <form onSubmit={handleCreateReport} className="mb-4">
            <div className="mb-2">
              <input
                className="form-control"
                placeholder="Report title"
                value={reportForm.title}
                onChange={(e) => setReportForm((s) => ({ ...s, title: e.target.value }))}
                required
              />
            </div>
            <div className="mb-2">
              <textarea
                className="form-control"
                rows={3}
                placeholder="Report details"
                value={reportForm.body}
                onChange={(e) => setReportForm((s) => ({ ...s, body: e.target.value }))}
                required
              />
            </div>
            <div className="row g-2 mb-2">
              <div className="col-4">
                <select
                  className="form-select"
                  value={reportForm.status}
                  onChange={(e) => setReportForm((s) => ({ ...s, status: e.target.value }))}
                >
                  <option value="open">Open</option>
                  <option value="closed">Closed</option>
                  <option value="monitoring">Monitoring</option>
                </select>
              </div>
              <div className="col-4">
                <input
                  className="form-control"
                  placeholder="Severity"
                  value={reportForm.severity}
                  onChange={(e) => setReportForm((s) => ({ ...s, severity: e.target.value }))}
                />
              </div>
              <div className="col-4">
                <input
                  className="form-control"
                  placeholder="Tags (comma-separated)"
                  value={reportForm.tags}
                  onChange={(e) => setReportForm((s) => ({ ...s, tags: e.target.value }))}
                />
              </div>
            </div>
            <button
              type="submit"
              className="btn btn-primary btn-sm"
              disabled={reportSaving || !reportForm.title.trim() || !reportForm.body.trim()}
            >
              {reportSaving ? 'Saving...' : 'Create Report'}
            </button>
          </form>
        )}

        <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-2">
          <div className="d-flex align-items-center gap-2">
            <span className="text-body-secondary" style={{ fontSize: '0.9rem' }}>
              Show
            </span>
            <select
              className="form-select form-select-sm"
              style={{ width: 90 }}
              value={pageSize}
              onChange={(e) => setPageSize(Number(e.target.value) || 10)}
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
            </select>
            <span className="text-body-secondary" style={{ fontSize: '0.9rem' }}>
              entries
            </span>
          </div>
          <form
            className="d-flex align-items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              setSearchQuery(searchInput.trim())
            }}
          >
            <label htmlFor="operator-reports-search" className="text-body-secondary" style={{ fontSize: '0.9rem' }}>
              Search:
            </label>
            <input
              id="operator-reports-search"
              className="form-control form-control-sm"
              style={{ width: 220 }}
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="title, comment, author"
            />
            <button type="submit" className="btn btn-sm btn-outline-secondary">
              Apply
            </button>
          </form>
        </div>

        {loadingReports ? (
          <div className="text-body-secondary">Loading reports...</div>
        ) : reports.length === 0 ? (
          <div className="text-body-secondary">No reports yet for this site.</div>
        ) : (
          <div className="table-responsive" style={{ maxHeight: 680, overflowY: 'auto' }}>
            <CTable hover small align="middle">
              <CTableHead>
                <CTableRow>
                  <CTableHeaderCell style={{ minWidth: 170 }}>Time</CTableHeaderCell>
                  <CTableHeaderCell style={{ minWidth: 180 }}>Name</CTableHeaderCell>
                  <CTableHeaderCell style={{ minWidth: 180 }}>Title</CTableHeaderCell>
                  <CTableHeaderCell style={{ minWidth: 420 }}>Comment</CTableHeaderCell>
                  <CTableHeaderCell style={{ minWidth: 160 }}>Status</CTableHeaderCell>
                  {isAdmin && <CTableHeaderCell style={{ minWidth: 140 }}>Actions</CTableHeaderCell>}
                </CTableRow>
              </CTableHead>
              <CTableBody>
                {reports.map((report) => {
                  const isEditing = editingReportId === report.id
                  return (
                    <React.Fragment key={report.id}>
                      <CTableRow>
                        <CTableDataCell className="text-body-secondary" style={{ verticalAlign: 'top' }}>
                          {formatReportDate(report.created_at)}
                        </CTableDataCell>
                        <CTableDataCell style={{ verticalAlign: 'top' }}>
                          {report.created_by?.name || report.created_by?.email || 'Unknown'}
                        </CTableDataCell>
                        <CTableDataCell style={{ verticalAlign: 'top' }}>
                          <div className="fw-semibold">{report.title}</div>
                          {report.tags?.length ? (
                            <div className="mt-1">
                              {report.tags.map((tag) => (
                                <CBadge key={`${report.id}:${tag}`} color="secondary" className="me-1">
                                  {tag}
                                </CBadge>
                              ))}
                            </div>
                          ) : null}
                        </CTableDataCell>
                        <CTableDataCell style={{ whiteSpace: 'pre-wrap', verticalAlign: 'top' }}>
                          {report.body}
                        </CTableDataCell>
                        <CTableDataCell style={{ verticalAlign: 'top' }}>
                          <CBadge color="light" textColor="dark" className="me-1">
                            {report.status || 'open'}
                          </CBadge>
                          {report.severity ? <CBadge color="warning">{report.severity}</CBadge> : null}
                        </CTableDataCell>
                        {isAdmin && (
                          <CTableDataCell style={{ verticalAlign: 'top' }}>
                            <div className="d-flex gap-2">
                              <button
                                type="button"
                                className="btn btn-sm btn-outline-primary"
                                onClick={() => startEditReport(report)}
                              >
                                Edit
                              </button>
                              <button
                                type="button"
                                className="btn btn-sm btn-outline-danger"
                                disabled={reportDeletingId === report.id}
                                onClick={() => handleDeleteReport(report.id)}
                              >
                                {reportDeletingId === report.id ? 'Deleting...' : 'Delete'}
                              </button>
                            </div>
                          </CTableDataCell>
                        )}
                      </CTableRow>
                      {isEditing && (
                        <CTableRow color="light">
                          <CTableDataCell colSpan={isAdmin ? 6 : 5}>
                            <div className="row g-2 mb-2">
                              <div className="col-md-4">
                                <input
                                  className="form-control form-control-sm"
                                  value={editingForm.title}
                                  onChange={(e) => setEditingForm((s) => ({ ...s, title: e.target.value }))}
                                  placeholder="Title"
                                />
                              </div>
                              <div className="col-md-3">
                                <select
                                  className="form-select form-select-sm"
                                  value={editingForm.status}
                                  onChange={(e) => setEditingForm((s) => ({ ...s, status: e.target.value }))}
                                >
                                  <option value="open">Open</option>
                                  <option value="closed">Closed</option>
                                  <option value="monitoring">Monitoring</option>
                                </select>
                              </div>
                              <div className="col-md-2">
                                <input
                                  className="form-control form-control-sm"
                                  value={editingForm.severity}
                                  onChange={(e) => setEditingForm((s) => ({ ...s, severity: e.target.value }))}
                                  placeholder="Severity"
                                />
                              </div>
                              <div className="col-md-3">
                                <input
                                  className="form-control form-control-sm"
                                  value={editingForm.tags}
                                  onChange={(e) => setEditingForm((s) => ({ ...s, tags: e.target.value }))}
                                  placeholder="Tags"
                                />
                              </div>
                            </div>
                            <div className="mb-2">
                              <textarea
                                className="form-control form-control-sm"
                                rows={4}
                                value={editingForm.body}
                                onChange={(e) => setEditingForm((s) => ({ ...s, body: e.target.value }))}
                              />
                            </div>
                            <div className="d-flex gap-2">
                              <button
                                type="button"
                                className="btn btn-sm btn-primary"
                                disabled={reportSaving}
                                onClick={() => handleUpdateReport(report.id)}
                              >
                                Save
                              </button>
                              <button
                                type="button"
                                className="btn btn-sm btn-outline-secondary"
                                disabled={reportSaving}
                                onClick={() => setEditingReportId(null)}
                              >
                                Cancel
                              </button>
                            </div>
                          </CTableDataCell>
                        </CTableRow>
                      )}
                    </React.Fragment>
                  )
                })}
              </CTableBody>
            </CTable>
          </div>
        )}

        {!loadingReports && (
          <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-2">
            <div className="text-body-secondary" style={{ fontSize: '0.85rem' }}>
              Showing {pageStart} to {pageEnd} of {totalReports} entries
            </div>
            <div className="d-flex align-items-center gap-2">
              <button
                type="button"
                className="btn btn-sm btn-outline-secondary"
                disabled={!canPrev}
                onClick={() => setPageOffset((v) => Math.max(0, v - pageSize))}
              >
                Previous
              </button>
              <span className="text-body-secondary" style={{ fontSize: '0.85rem' }}>
                Page {currentPage} / {totalPages}
              </span>
              <button
                type="button"
                className="btn btn-sm btn-outline-secondary"
                disabled={!canNext}
                onClick={() => setPageOffset((v) => v + pageSize)}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </CCardBody>
    </CCard>
  )
}

export default OperatorReportsPanel
