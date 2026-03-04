import React, { useEffect, useState } from 'react'
import {
  CCard,
  CCardBody,
  CCardHeader,
  CCol,
  CRow,
  CTable,
  CTableBody,
  CTableDataCell,
  CTableHead,
  CTableHeaderCell,
  CTableRow,
} from '@coreui/react'
import { createUser, deleteUser, listUsers, updateUser } from '../../api/users'
import { getMe } from '../../api/auth'

const ROLE_OPTIONS = [
  { value: 0, label: 'admin' },
  { value: 1, label: 'labmember' },
  { value: 2, label: 'public' },
]

const roleLabel = (role) => {
  const hit = ROLE_OPTIONS.find((r) => r.value === Number(role))
  if (!hit) return `unknown (${role})`
  return `${hit.value} ${hit.label}`
}

const UserManagement = () => {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)
  const [createForm, setCreateForm] = useState({ email: '', role: 1 })
  const [editingId, setEditingId] = useState(null)
  const [editingForm, setEditingForm] = useState({ email: '', role: 1 })
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState(null)

  const loadUsers = async (signal) => {
    setError('')
    const me = await getMe({ signal })
    setIsAdmin(Boolean(me?.isAdmin))
    const payload = await listUsers({ signal })
    setUsers(Array.isArray(payload?.users) ? payload.users : [])
  }

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setLoading(true)
    loadUsers(controller.signal)
      .catch((err) => {
        if (!active || err?.name === 'AbortError') return
        setUsers([])
        setError(err?.message || 'Failed to load users')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [])

  const startEdit = (user) => {
    setEditingId(user.id)
    setEditingForm({ email: user.email || '', role: Number(user.role) })
    setError('')
  }

  const submitCreate = async (e) => {
    e.preventDefault()
    if (!isAdmin) return
    setSaving(true)
    setError('')
    try {
      await createUser({
        email: createForm.email.trim(),
        role: Number(createForm.role),
      })
      setCreateForm({ email: '', role: 1 })
      await loadUsers()
    } catch (err) {
      setError(err?.message || 'Failed to create user')
    } finally {
      setSaving(false)
    }
  }

  const submitEdit = async (id) => {
    if (!isAdmin) return
    setSaving(true)
    setError('')
    try {
      await updateUser(id, {
        email: editingForm.email.trim(),
        role: Number(editingForm.role),
      })
      setEditingId(null)
      await loadUsers()
    } catch (err) {
      setError(err?.message || 'Failed to update user')
    } finally {
      setSaving(false)
    }
  }

  const submitDelete = async (id) => {
    if (!isAdmin) return
    if (!window.confirm('Delete this user?')) return
    setDeletingId(id)
    setError('')
    try {
      await deleteUser(id)
      if (editingId === id) setEditingId(null)
      await loadUsers()
    } catch (err) {
      setError(err?.message || 'Failed to delete user')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <CRow>
      <CCol>
        <CCard>
          <CCardHeader>User Management</CCardHeader>
          <CCardBody>
            <div className="text-body-secondary mb-3" style={{ fontSize: '0.9rem' }}>
              Google OAuth remains the login provider. This page controls which users are allowed and their role.
            </div>
            <div className="text-body-secondary mb-3" style={{ fontSize: '0.9rem' }}>
              Roles: <strong>0</strong> admin, <strong>1</strong> labmember, <strong>2</strong> public.
            </div>
            {error && <div className="text-danger mb-3">{error}</div>}
            {!isAdmin && !loading ? (
              <div className="text-danger mb-3">Only admins can manage users.</div>
            ) : null}

            {isAdmin ? (
              <form onSubmit={submitCreate} className="row g-2 mb-4">
                <div className="col-md-6">
                  <input
                    className="form-control"
                    placeholder="user@email.com"
                    value={createForm.email}
                    onChange={(e) => setCreateForm((s) => ({ ...s, email: e.target.value }))}
                    required
                  />
                </div>
                <div className="col-md-3">
                  <select
                    className="form-select"
                    value={createForm.role}
                    onChange={(e) => setCreateForm((s) => ({ ...s, role: Number(e.target.value) }))}
                  >
                    {ROLE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.value} {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-md-3">
                  <button
                    type="submit"
                    className="btn btn-primary w-100"
                    disabled={saving || !createForm.email.trim()}
                  >
                    {saving ? 'Saving...' : 'Add User'}
                  </button>
                </div>
              </form>
            ) : null}

            {loading ? (
              <div className="text-body-secondary">Loading users...</div>
            ) : (
              <div className="table-responsive">
                <CTable hover small>
                  <CTableHead>
                    <CTableRow>
                      <CTableHeaderCell style={{ minWidth: 100 }}>ID</CTableHeaderCell>
                      <CTableHeaderCell style={{ minWidth: 300 }}>Email</CTableHeaderCell>
                      <CTableHeaderCell style={{ minWidth: 180 }}>Role</CTableHeaderCell>
                      {isAdmin && <CTableHeaderCell style={{ minWidth: 200 }}>Actions</CTableHeaderCell>}
                    </CTableRow>
                  </CTableHead>
                  <CTableBody>
                    {users.map((user) => {
                      const isEditing = editingId === user.id
                      return (
                        <React.Fragment key={user.id}>
                          <CTableRow>
                            <CTableDataCell>{user.id}</CTableDataCell>
                            <CTableDataCell>{user.email}</CTableDataCell>
                            <CTableDataCell>{roleLabel(user.role)}</CTableDataCell>
                            {isAdmin && (
                              <CTableDataCell>
                                <div className="d-flex gap-2">
                                  <button
                                    type="button"
                                    className="btn btn-sm btn-outline-primary"
                                    onClick={() => startEdit(user)}
                                  >
                                    Edit
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-sm btn-outline-danger"
                                    disabled={deletingId === user.id}
                                    onClick={() => submitDelete(user.id)}
                                  >
                                    {deletingId === user.id ? 'Deleting...' : 'Delete'}
                                  </button>
                                </div>
                              </CTableDataCell>
                            )}
                          </CTableRow>
                          {isAdmin && isEditing && (
                            <CTableRow color="light">
                              <CTableDataCell colSpan={4}>
                                <div className="row g-2">
                                  <div className="col-md-6">
                                    <input
                                      className="form-control form-control-sm"
                                      value={editingForm.email}
                                      onChange={(e) =>
                                        setEditingForm((s) => ({ ...s, email: e.target.value }))
                                      }
                                      placeholder="user@email.com"
                                    />
                                  </div>
                                  <div className="col-md-3">
                                    <select
                                      className="form-select form-select-sm"
                                      value={editingForm.role}
                                      onChange={(e) =>
                                        setEditingForm((s) => ({ ...s, role: Number(e.target.value) }))
                                      }
                                    >
                                      {ROLE_OPTIONS.map((option) => (
                                        <option key={option.value} value={option.value}>
                                          {option.value} {option.label}
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                  <div className="col-md-3 d-flex gap-2">
                                    <button
                                      type="button"
                                      className="btn btn-sm btn-primary flex-fill"
                                      disabled={saving}
                                      onClick={() => submitEdit(user.id)}
                                    >
                                      Save
                                    </button>
                                    <button
                                      type="button"
                                      className="btn btn-sm btn-outline-secondary flex-fill"
                                      disabled={saving}
                                      onClick={() => setEditingId(null)}
                                    >
                                      Cancel
                                    </button>
                                  </div>
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
          </CCardBody>
        </CCard>
      </CCol>
    </CRow>
  )
}

export default UserManagement
