import React, { useEffect, useState } from 'react'
import {
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
  createGrabSample,
  deleteGrabSample,
  listGrabSamples,
  updateGrabSample,
} from '../api/grabSamples'

const EMPTY_FORM = {
  extracted_at: '',
  arrived_at: '',
  sample_taken_by: '',
  raw_file_name: '',
  storage_provider: 's3',
  storage_bucket: '',
  storage_key: '',
  file_url: '',
  parse_status: 'pending',
  notes: '',
}

function toLocalInputValue(raw) {
  if (!raw) return ''
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return ''
  const offsetMs = d.getTimezoneOffset() * 60 * 1000
  return new Date(d.getTime() - offsetMs).toISOString().slice(0, 16)
}

function fromLocalInputValue(raw) {
  if (!raw) return ''
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return ''
  return d.toISOString()
}

function formatDate(raw) {
  if (!raw) return 'Not set'
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return 'Not set'
  return d.toLocaleString()
}

function storageSummary(sample) {
  const parts = [sample.storage_provider, sample.storage_bucket, sample.storage_key].filter(Boolean)
  if (parts.length) return parts.join(' / ')
  if (sample.file_url) return 'External URL'
  return 'Unassigned'
}

const GrabSamplesPanel = ({ siteKey }) => {
  const [isAdmin, setIsAdmin] = useState(false)
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState([])
  const [error, setError] = useState('')
  const [saveError, setSaveError] = useState('')
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [editingId, setEditingId] = useState(null)
  const [editingForm, setEditingForm] = useState(EMPTY_FORM)
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

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
    setLoading(true)
    setError('')
    listGrabSamples(siteKey, { q: searchQuery, signal: controller.signal })
      .then((payload) => {
        if (!active) return
        setItems(Array.isArray(payload?.grab_samples) ? payload.grab_samples : [])
      })
      .catch((err) => {
        if (!active || err?.name === 'AbortError') return
        setItems([])
        setError(err?.message || 'Failed to load grab samples')
      })
      .finally(() => {
        if (!active) return
        setLoading(false)
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [siteKey, searchQuery])

  const reload = async () => {
    const payload = await listGrabSamples(siteKey, { q: searchQuery })
    setItems(Array.isArray(payload?.grab_samples) ? payload.grab_samples : [])
  }

  const startEdit = (sample) => {
    setEditingId(sample.id)
    setEditingForm({
      extracted_at: toLocalInputValue(sample.extracted_at),
      arrived_at: toLocalInputValue(sample.arrived_at),
      sample_taken_by: sample.sample_taken_by || '',
      raw_file_name: sample.raw_file_name || '',
      storage_provider: sample.storage_provider || 's3',
      storage_bucket: sample.storage_bucket || '',
      storage_key: sample.storage_key || '',
      file_url: sample.file_url || '',
      parse_status: sample.parse_status || 'pending',
      notes: sample.notes || '',
    })
    setSaveError('')
  }

  const handleCreate = async (event) => {
    event.preventDefault()
    setSaving(true)
    setSaveError('')
    try {
      await createGrabSample(siteKey, {
        ...form,
        extracted_at: fromLocalInputValue(form.extracted_at),
        arrived_at: fromLocalInputValue(form.arrived_at),
      })
      setForm(EMPTY_FORM)
      await reload()
    } catch (err) {
      setSaveError(err?.message || 'Failed to create grab sample')
    } finally {
      setSaving(false)
    }
  }

  const handleUpdate = async (id) => {
    setSaving(true)
    setSaveError('')
    try {
      await updateGrabSample(siteKey, id, {
        ...editingForm,
        extracted_at: fromLocalInputValue(editingForm.extracted_at),
        arrived_at: fromLocalInputValue(editingForm.arrived_at),
      })
      setEditingId(null)
      await reload()
    } catch (err) {
      setSaveError(err?.message || 'Failed to update grab sample')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this grab sample record?')) return
    setDeletingId(id)
    setSaveError('')
    try {
      await deleteGrabSample(siteKey, id)
      if (editingId === id) setEditingId(null)
      await reload()
    } catch (err) {
      setSaveError(err?.message || 'Failed to delete grab sample')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <CCard className="mt-4">
      <CCardHeader>Grab Samples</CCardHeader>
      <CCardBody>
        <div className="text-body-secondary mb-3" style={{ fontSize: '0.9rem' }}>
          Legacy grab-sample records now live here under System Management. This panel stores sample metadata
          and raw-file references for Excel archives so parsed chemistry can be migrated into TimescaleDB
          separately.
        </div>
        {error && <div className="text-danger mb-2">{error}</div>}
        {saveError && <div className="text-danger mb-2">{saveError}</div>}

        {isAdmin && (
          <form onSubmit={handleCreate} className="mb-4">
            <div className="row g-2 mb-2">
              <div className="col-md-3">
                <label className="form-label">Sample Collection Date</label>
                <input
                  className="form-control"
                  type="datetime-local"
                  value={form.extracted_at}
                  onChange={(e) => setForm((s) => ({ ...s, extracted_at: e.target.value }))}
                />
              </div>
              <div className="col-md-3">
                <label className="form-label">Sample Arrival Date</label>
                <input
                  className="form-control"
                  type="datetime-local"
                  value={form.arrived_at}
                  onChange={(e) => setForm((s) => ({ ...s, arrived_at: e.target.value }))}
                />
              </div>
              <div className="col-md-3">
                <label className="form-label">Taken/Delivered By</label>
                <input
                  className="form-control"
                  value={form.sample_taken_by}
                  onChange={(e) => setForm((s) => ({ ...s, sample_taken_by: e.target.value }))}
                />
              </div>
              <div className="col-md-3">
                <label className="form-label">Raw File Name</label>
                <input
                  className="form-control"
                  value={form.raw_file_name}
                  onChange={(e) => setForm((s) => ({ ...s, raw_file_name: e.target.value }))}
                  placeholder="sample.xlsx"
                />
              </div>
            </div>
            <div className="row g-2 mb-2">
              <div className="col-md-2">
                <label className="form-label">Storage</label>
                <select
                  className="form-select"
                  value={form.storage_provider}
                  onChange={(e) => setForm((s) => ({ ...s, storage_provider: e.target.value }))}
                >
                  <option value="s3">S3</option>
                  <option value="local">Local</option>
                  <option value="url">URL</option>
                  <option value="manual">Manual</option>
                </select>
              </div>
              <div className="col-md-3">
                <label className="form-label">Bucket</label>
                <input
                  className="form-control"
                  value={form.storage_bucket}
                  onChange={(e) => setForm((s) => ({ ...s, storage_bucket: e.target.value }))}
                />
              </div>
              <div className="col-md-3">
                <label className="form-label">Object Key</label>
                <input
                  className="form-control"
                  value={form.storage_key}
                  onChange={(e) => setForm((s) => ({ ...s, storage_key: e.target.value }))}
                  placeholder="grab-samples/site/file.xlsx"
                />
              </div>
              <div className="col-md-2">
                <label className="form-label">Parse Status</label>
                <select
                  className="form-select"
                  value={form.parse_status}
                  onChange={(e) => setForm((s) => ({ ...s, parse_status: e.target.value }))}
                >
                  <option value="pending">Pending</option>
                  <option value="parsed">Parsed</option>
                  <option value="failed">Failed</option>
                  <option value="manual">Manual</option>
                </select>
              </div>
              <div className="col-md-2">
                <label className="form-label">External URL</label>
                <input
                  className="form-control"
                  value={form.file_url}
                  onChange={(e) => setForm((s) => ({ ...s, file_url: e.target.value }))}
                  placeholder="https://..."
                />
              </div>
            </div>
            <div className="mb-2">
              <label className="form-label">Notes</label>
              <textarea
                className="form-control"
                rows={2}
                value={form.notes}
                onChange={(e) => setForm((s) => ({ ...s, notes: e.target.value }))}
                placeholder="Lab notes, parsing remarks, or migration context"
              />
            </div>
            <button type="submit" className="btn btn-primary btn-sm" disabled={saving}>
              {saving ? 'Saving...' : 'Store Sample Metadata'}
            </button>
          </form>
        )}

        <div className="d-flex justify-content-between align-items-center gap-2 mb-3">
          <div className="text-body-secondary" style={{ fontSize: '0.9rem' }}>
            Archived sample records for the selected site.
          </div>
          <div className="d-flex gap-2">
            <input
              className="form-control form-control-sm"
              style={{ width: 260 }}
              placeholder="Search sample id, file, notes"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
            <button className="btn btn-outline-secondary btn-sm" onClick={() => setSearchQuery(searchInput.trim())}>
              Search
            </button>
          </div>
        </div>

        {loading ? (
          <div className="text-body-secondary">Loading grab samples...</div>
        ) : (
          <CTable hover responsive small>
            <CTableHead>
              <CTableRow>
                <CTableHeaderCell>Sample ID</CTableHeaderCell>
                <CTableHeaderCell>Collection Date</CTableHeaderCell>
                <CTableHeaderCell>Arrival Date</CTableHeaderCell>
                <CTableHeaderCell>Taken/Delivered By</CTableHeaderCell>
                <CTableHeaderCell>Raw File</CTableHeaderCell>
                <CTableHeaderCell>Storage</CTableHeaderCell>
                <CTableHeaderCell>Status</CTableHeaderCell>
                <CTableHeaderCell>Actions</CTableHeaderCell>
              </CTableRow>
            </CTableHead>
            <CTableBody>
              {items.map((sample) => {
                const editing = editingId === sample.id
                return (
                  <CTableRow key={sample.id}>
                    <CTableDataCell className="fw-semibold">{sample.sample_id}</CTableDataCell>
                    <CTableDataCell>
                      {editing ? (
                        <input
                          className="form-control form-control-sm"
                          type="datetime-local"
                          value={editingForm.extracted_at}
                          onChange={(e) => setEditingForm((s) => ({ ...s, extracted_at: e.target.value }))}
                        />
                      ) : (
                        formatDate(sample.extracted_at)
                      )}
                    </CTableDataCell>
                    <CTableDataCell>
                      {editing ? (
                        <input
                          className="form-control form-control-sm"
                          type="datetime-local"
                          value={editingForm.arrived_at}
                          onChange={(e) => setEditingForm((s) => ({ ...s, arrived_at: e.target.value }))}
                        />
                      ) : (
                        formatDate(sample.arrived_at)
                      )}
                    </CTableDataCell>
                    <CTableDataCell>
                      {editing ? (
                        <input
                          className="form-control form-control-sm"
                          value={editingForm.sample_taken_by}
                          onChange={(e) => setEditingForm((s) => ({ ...s, sample_taken_by: e.target.value }))}
                        />
                      ) : (
                        sample.sample_taken_by || 'Unknown'
                      )}
                    </CTableDataCell>
                    <CTableDataCell>
                      {editing ? (
                        <div className="d-grid gap-1">
                          <input
                            className="form-control form-control-sm"
                            value={editingForm.raw_file_name}
                            onChange={(e) => setEditingForm((s) => ({ ...s, raw_file_name: e.target.value }))}
                            placeholder="sample.xlsx"
                          />
                          <input
                            className="form-control form-control-sm"
                            value={editingForm.file_url}
                            onChange={(e) => setEditingForm((s) => ({ ...s, file_url: e.target.value }))}
                            placeholder="https://..."
                          />
                        </div>
                      ) : sample.file_url ? (
                        <a href={sample.file_url} target="_blank" rel="noreferrer">
                          {sample.raw_file_name || 'Open file'}
                        </a>
                      ) : (
                        sample.raw_file_name || 'No file'
                      )}
                    </CTableDataCell>
                    <CTableDataCell>
                      {editing ? (
                        <div className="d-grid gap-1">
                          <select
                            className="form-select form-select-sm"
                            value={editingForm.storage_provider}
                            onChange={(e) => setEditingForm((s) => ({ ...s, storage_provider: e.target.value }))}
                          >
                            <option value="s3">S3</option>
                            <option value="local">Local</option>
                            <option value="url">URL</option>
                            <option value="manual">Manual</option>
                          </select>
                          <input
                            className="form-control form-control-sm"
                            value={editingForm.storage_bucket}
                            onChange={(e) => setEditingForm((s) => ({ ...s, storage_bucket: e.target.value }))}
                            placeholder="bucket"
                          />
                          <input
                            className="form-control form-control-sm"
                            value={editingForm.storage_key}
                            onChange={(e) => setEditingForm((s) => ({ ...s, storage_key: e.target.value }))}
                            placeholder="object key"
                          />
                        </div>
                      ) : (
                        storageSummary(sample)
                      )}
                    </CTableDataCell>
                    <CTableDataCell>
                      {editing ? (
                        <select
                          className="form-select form-select-sm"
                          value={editingForm.parse_status}
                          onChange={(e) => setEditingForm((s) => ({ ...s, parse_status: e.target.value }))}
                        >
                          <option value="pending">Pending</option>
                          <option value="parsed">Parsed</option>
                          <option value="failed">Failed</option>
                          <option value="manual">Manual</option>
                        </select>
                      ) : (
                        sample.parse_status || 'pending'
                      )}
                    </CTableDataCell>
                    <CTableDataCell style={{ minWidth: 180 }}>
                      {editing ? (
                        <div className="d-grid gap-1">
                          <textarea
                            className="form-control form-control-sm"
                            rows={2}
                            value={editingForm.notes}
                            onChange={(e) => setEditingForm((s) => ({ ...s, notes: e.target.value }))}
                          />
                          <div className="d-flex gap-1">
                            <button
                              className="btn btn-primary btn-sm"
                              onClick={() => handleUpdate(sample.id)}
                              disabled={saving}
                            >
                              Save
                            </button>
                            <button
                              className="btn btn-outline-secondary btn-sm"
                              onClick={() => setEditingId(null)}
                              disabled={saving}
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="d-flex gap-1 align-items-start">
                          {isAdmin && (
                            <button className="btn btn-outline-primary btn-sm" onClick={() => startEdit(sample)}>
                              Edit
                            </button>
                          )}
                          {isAdmin && (
                            <button
                              className="btn btn-outline-danger btn-sm"
                              onClick={() => handleDelete(sample.id)}
                              disabled={deletingId === sample.id}
                            >
                              {deletingId === sample.id ? 'Deleting...' : 'Delete'}
                            </button>
                          )}
                        </div>
                      )}
                    </CTableDataCell>
                  </CTableRow>
                )
              })}
              {!items.length && (
                <CTableRow>
                  <CTableDataCell colSpan={8} className="text-body-secondary text-center py-4">
                    No grab samples recorded for this site yet.
                  </CTableDataCell>
                </CTableRow>
              )}
            </CTableBody>
          </CTable>
        )}
      </CCardBody>
    </CCard>
  )
}

export default GrabSamplesPanel
