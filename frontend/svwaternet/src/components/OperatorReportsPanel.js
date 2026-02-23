import React, { useEffect, useState } from 'react'
import { CCard, CCardBody, CCardHeader } from '@coreui/react'
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

  useEffect(() => {
    const controller = new AbortController()
    getMe({ signal: controller.signal })
      .then((payload) => setIsAdmin(Boolean(payload?.isAdmin)))
      .catch(() => setIsAdmin(false))
    return () => controller.abort()
  }, [])

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setLoadingReports(true)
    setReportsError('')
    listOperatorReports(siteKey, { limit: 20, signal: controller.signal })
      .then((payload) => {
        if (!active) return
        setReports(Array.isArray(payload?.reports) ? payload.reports : [])
      })
      .catch((err) => {
        if (!active || err?.name === 'AbortError') return
        setReports([])
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
  }, [siteKey])

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
    const payload = await listOperatorReports(siteKey, { limit: 20 })
    setReports(Array.isArray(payload?.reports) ? payload.reports : [])
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

        {loadingReports ? (
          <div className="text-body-secondary">Loading reports...</div>
        ) : reports.length === 0 ? (
          <div className="text-body-secondary">No reports yet for this site.</div>
        ) : (
          <div style={{ maxHeight: 680, overflowY: 'auto' }}>
            {reports.map((report) => {
              const isEditing = editingReportId === report.id
              return (
                <div key={report.id} className="border rounded p-2 mb-2">
                  {isEditing ? (
                    <>
                      <div className="mb-2">
                        <input
                          className="form-control form-control-sm"
                          value={editingForm.title}
                          onChange={(e) => setEditingForm((s) => ({ ...s, title: e.target.value }))}
                        />
                      </div>
                      <div className="mb-2">
                        <textarea
                          className="form-control form-control-sm"
                          rows={3}
                          value={editingForm.body}
                          onChange={(e) => setEditingForm((s) => ({ ...s, body: e.target.value }))}
                        />
                      </div>
                      <div className="row g-2 mb-2">
                        <div className="col-4">
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
                        <div className="col-4">
                          <input
                            className="form-control form-control-sm"
                            value={editingForm.severity}
                            onChange={(e) => setEditingForm((s) => ({ ...s, severity: e.target.value }))}
                            placeholder="Severity"
                          />
                        </div>
                        <div className="col-4">
                          <input
                            className="form-control form-control-sm"
                            value={editingForm.tags}
                            onChange={(e) => setEditingForm((s) => ({ ...s, tags: e.target.value }))}
                            placeholder="Tags"
                          />
                        </div>
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
                    </>
                  ) : (
                    <>
                      <div className="d-flex justify-content-between align-items-start gap-2">
                        <div>
                          <div className="fw-semibold">{report.title}</div>
                          <div className="text-body-secondary" style={{ fontSize: '0.8rem' }}>
                            {formatReportDate(report.created_at)}
                            {report.created_by?.email ? ` • ${report.created_by.email}` : ''}
                          </div>
                        </div>
                        <div className="text-end">
                          <span className="badge text-bg-light me-1">{report.status || 'open'}</span>
                          {report.severity ? <span className="badge text-bg-warning">{report.severity}</span> : null}
                        </div>
                      </div>
                      <div className="mt-2" style={{ whiteSpace: 'pre-wrap', fontSize: '0.92rem' }}>
                        {report.body}
                      </div>
                      {Array.isArray(report.tags) && report.tags.length > 0 && (
                        <div className="mt-2">
                          {report.tags.map((tag) => (
                            <span key={`${report.id}:${tag}`} className="badge text-bg-secondary me-1">
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                      {isAdmin && (
                        <div className="mt-2 d-flex gap-2">
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
                      )}
                    </>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </CCardBody>
    </CCard>
  )
}

export default OperatorReportsPanel

