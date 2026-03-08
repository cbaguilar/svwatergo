import React, { useMemo, useState } from 'react'
import { useSelector } from 'react-redux'
import {
  CAlert,
  CButton,
  CButtonGroup,
  CCard,
  CCardBody,
  CCardHeader,
  CCol,
  CFormCheck,
  CFormInput,
  CFormLabel,
  CFormSelect,
  CRow,
  CSpinner,
} from '@coreui/react'
import { generateAlertFormPdf } from '../../api/alertForms'

const SITE_BY_SYSTEM = {
  Bluerock: 'bluerock',
  'Santa Teresa': 'santateresa',
  'Pryor Farms': 'pryorfarm',
}

const ALERT_TYPES = [
  { key: 'notProducing', label: 'Not Producing' },
  { key: 'highNitrates', label: 'High Nitrates' },
  { key: 'bacteria', label: 'Bacteria' },
  { key: 'contamination', label: 'Contamination' },
  { key: 'resolved', label: 'Resolved' },
]

const ALERT_DETAIL_OPTIONS = [
  { key: 'wellRepair', label: 'The well needs to be repaired' },
  { key: 'connectionRepair', label: 'The connection from the well to the treatment system needs to be repaired' },
  { key: 'highBacteria', label: 'Regular testing showed that there were bacteria in the water system and this problem had to be addressed' },
  { key: 'systemRepair', label: 'The water treatment system had to be repaired' },
  { key: 'powerOut', label: 'The power is out and the pumps necessary for delivering water were not working properly and the problem had to be repaired' },
  { key: 'custom', label: 'Custom Detail' },
]

const RESPONSE_DETAIL_OPTIONS = [
  {
    key: 'daysWaterLeft',
    label: 'Reduce Water: The Water Storage Tank has a limited number of days of supplies for normal usage.',
  },
  { key: 'stopUsage', label: 'Stop drinking or cooking with tap water while the system is being cleaned.' },
]

const REPLACEMENT_DETAIL_OPTIONS = [
  { key: 'waterHaul', label: 'Expect that drinking water will be hauled to the site to replenish stored treated water' },
  { key: 'useBottled', label: 'Until further notice, purchase and ONLY use bottled water' },
  { key: 'bottleDelivery', label: 'Bottled water will be delivered' },
]

const RECIPIENT_GROUP_OPTIONS = [
  'UCLA WaTeR Group',
  'State of California',
  'Residents',
  'Rick Sagin',
  'Babette Sagin',
]

const BASE_FORM = {
  alertDetails: [],
  customDetail: '',
  responseDetails: [],
  daysWaterLeft: '',
  replacementDetails: [],
  issueDate: '',
  resolveDate: '',
  noticeDate: '',
  substance: '',
  incident: '',
  location: '',
  recipientGroups: ['UCLA WaTeR Group'],
}

const FORM_TEMPLATES = {
  notProducing: {
    ...BASE_FORM,
    alertDetails: ['wellRepair'],
    responseDetails: ['daysWaterLeft'],
    daysWaterLeft: '3',
  },
  highNitrates: {
    ...BASE_FORM,
  },
  bacteria: {
    ...BASE_FORM,
  },
  contamination: {
    ...BASE_FORM,
  },
  resolved: {
    ...BASE_FORM,
    alertDetails: ['wellRepair'],
    responseDetails: ['stopUsage'],
  },
}

function templateForType(alertType) {
  const template = FORM_TEMPLATES[alertType] || BASE_FORM
  return {
    ...template,
    alertDetails: [...template.alertDetails],
    responseDetails: [...template.responseDetails],
    replacementDetails: [...template.replacementDetails],
    recipientGroups: [...template.recipientGroups],
  }
}

function toggleArrayValue(items, value) {
  if (items.includes(value)) {
    return items.filter((entry) => entry !== value)
  }
  return [...items, value]
}

function toPdfFilename(alertType) {
  const stamp = new Date().toISOString().replaceAll(':', '-')
  return `alert-form-${alertType}-${stamp}.pdf`
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

const AlertForms = () => {
  const selectedSystem = useSelector((state) => state.selectedSystem)
  const siteKey = SITE_BY_SYSTEM[selectedSystem] || 'bluerock'

  const [activeType, setActiveType] = useState('notProducing')
  const [form, setForm] = useState(templateForType('notProducing'))
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const showLongFormSections = useMemo(
    () => activeType === 'notProducing' || activeType === 'resolved',
    [activeType],
  )

  const showIssueResolveDates = useMemo(
    () => activeType === 'highNitrates' || activeType === 'bacteria' || activeType === 'contamination',
    [activeType],
  )

  const showContaminationFields = activeType === 'contamination'

  const onSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setSuccess('')

    if (!form.recipientGroups.length) {
      setError('Select at least one recipient group.')
      return
    }
    if (
      form.responseDetails.includes('daysWaterLeft') &&
      (form.daysWaterLeft === '' || Number(form.daysWaterLeft) < 0)
    ) {
      setError('Enter a valid number of days for water supply.')
      return
    }
    if (form.alertDetails.includes('custom') && !form.customDetail.trim()) {
      setError('Custom detail is required when Custom Detail is selected.')
      return
    }

    const payload = {
      alertType: activeType,
      alertDetails: form.alertDetails,
      customDetail: form.customDetail,
      responseDetails: form.responseDetails,
      daysWaterLeft:
        form.responseDetails.includes('daysWaterLeft') && form.daysWaterLeft !== ''
          ? Number(form.daysWaterLeft)
          : null,
      replacementDetails: form.replacementDetails,
      issueDate: form.issueDate,
      resolveDate: form.resolveDate,
      noticeDate: form.noticeDate,
      substance: form.substance,
      incident: form.incident,
      location: form.location,
      recipientGroups: form.recipientGroups,
    }

    setSubmitting(true)
    try {
      const blob = await generateAlertFormPdf(siteKey, payload)
      downloadBlob(blob, toPdfFilename(activeType))
      setSuccess('PDF generated and downloaded.')
    } catch (err) {
      setError(err?.message || 'Failed to generate PDF.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <CRow>
      <CCol xs={12}>
        <CCard>
          <CCardHeader>Alert Forms</CCardHeader>
          <CCardBody>
            <div className="mb-3">
              <CFormLabel>Alert form type</CFormLabel>
              <br />
              <CButtonGroup role="group" aria-label="Alert form type">
                {ALERT_TYPES.map((type) => (
                  <CButton
                    key={type.key}
                    color={activeType === type.key ? 'primary' : 'secondary'}
                    variant={activeType === type.key ? undefined : 'outline'}
                    onClick={() => {
                      setActiveType(type.key)
                      setForm(templateForType(type.key))
                    }}
                    disabled={submitting}
                  >
                    {type.label}
                  </CButton>
                ))}
              </CButtonGroup>
            </div>

            {error ? <CAlert color="danger">{error}</CAlert> : null}
            {success ? <CAlert color="success">{success}</CAlert> : null}

            <form onSubmit={onSubmit}>
              {showLongFormSections ? (
                <>
                  <div className="mb-3">
                    <CFormLabel>Alert Details</CFormLabel>
                    {ALERT_DETAIL_OPTIONS.map((option) => (
                      <CFormCheck
                        key={option.key}
                        id={`alert-detail-${option.key}`}
                        className="mb-2"
                        label={option.label}
                        checked={form.alertDetails.includes(option.key)}
                        onChange={() =>
                          setForm((prev) => ({
                            ...prev,
                            alertDetails: toggleArrayValue(prev.alertDetails, option.key),
                          }))
                        }
                      />
                    ))}
                    {form.alertDetails.includes('custom') ? (
                      <CFormInput
                        className="mt-2"
                        placeholder="Custom detail"
                        value={form.customDetail}
                        onChange={(event) =>
                          setForm((prev) => ({ ...prev, customDetail: event.target.value }))
                        }
                      />
                    ) : null}
                  </div>

                  <div className="mb-3">
                    <CFormLabel>{activeType === 'resolved' ? 'Resolution Details' : 'Response Details'}</CFormLabel>
                    {activeType === 'resolved' ? (
                      <CFormInput
                        type="date"
                        className="mb-3"
                        value={form.noticeDate}
                        onChange={(event) =>
                          setForm((prev) => ({ ...prev, noticeDate: event.target.value }))
                        }
                      />
                    ) : null}
                    {RESPONSE_DETAIL_OPTIONS.map((option) => (
                      <CFormCheck
                        key={option.key}
                        id={`response-detail-${option.key}`}
                        className="mb-2"
                        label={option.label}
                        checked={form.responseDetails.includes(option.key)}
                        onChange={() =>
                          setForm((prev) => ({
                            ...prev,
                            responseDetails: toggleArrayValue(prev.responseDetails, option.key),
                          }))
                        }
                      />
                    ))}
                    {form.responseDetails.includes('daysWaterLeft') ? (
                      <CFormInput
                        type="number"
                        min={0}
                        className="mt-2"
                        placeholder="Number of days"
                        value={form.daysWaterLeft}
                        onChange={(event) =>
                          setForm((prev) => ({ ...prev, daysWaterLeft: event.target.value }))
                        }
                      />
                    ) : null}
                  </div>

                  <div className="mb-3">
                    <CFormLabel>Replacement Details</CFormLabel>
                    {REPLACEMENT_DETAIL_OPTIONS.map((option) => (
                      <CFormCheck
                        key={option.key}
                        id={`replacement-detail-${option.key}`}
                        className="mb-2"
                        label={option.label}
                        checked={form.replacementDetails.includes(option.key)}
                        onChange={() =>
                          setForm((prev) => ({
                            ...prev,
                            replacementDetails: toggleArrayValue(prev.replacementDetails, option.key),
                          }))
                        }
                      />
                    ))}
                  </div>
                </>
              ) : null}

              {showIssueResolveDates ? (
                <>
                  <div className="mb-3">
                    <CFormLabel>Issue Date</CFormLabel>
                    <CFormInput
                      type="date"
                      value={form.issueDate}
                      onChange={(event) => setForm((prev) => ({ ...prev, issueDate: event.target.value }))}
                    />
                  </div>
                  <div className="mb-3">
                    <CFormLabel>Expected Resolve Date</CFormLabel>
                    <CFormInput
                      type="date"
                      value={form.resolveDate}
                      onChange={(event) => setForm((prev) => ({ ...prev, resolveDate: event.target.value }))}
                    />
                  </div>
                </>
              ) : null}

              {showContaminationFields ? (
                <>
                  <div className="mb-3">
                    <CFormLabel>Suspected Substance</CFormLabel>
                    <CFormInput
                      value={form.substance}
                      onChange={(event) => setForm((prev) => ({ ...prev, substance: event.target.value }))}
                    />
                  </div>
                  <div className="mb-3">
                    <CFormLabel>Incident Type</CFormLabel>
                    <CFormInput
                      value={form.incident}
                      onChange={(event) => setForm((prev) => ({ ...prev, incident: event.target.value }))}
                    />
                  </div>
                  <div className="mb-3">
                    <CFormLabel>Incident Location</CFormLabel>
                    <CFormInput
                      value={form.location}
                      onChange={(event) => setForm((prev) => ({ ...prev, location: event.target.value }))}
                    />
                  </div>
                </>
              ) : null}

              <div className="mb-4">
                <CFormLabel>Recipient Groups</CFormLabel>
                <CFormSelect
                  multiple
                  value={form.recipientGroups}
                  onChange={(event) => {
                    const groups = Array.from(event.target.selectedOptions).map((option) => option.value)
                    setForm((prev) => ({ ...prev, recipientGroups: groups }))
                  }}
                >
                  {RECIPIENT_GROUP_OPTIONS.map((group) => (
                    <option key={group} value={group}>
                      {group}
                    </option>
                  ))}
                </CFormSelect>
                <small className="text-body-secondary">Hold Ctrl (or Cmd on Mac) to select multiple.</small>
              </div>

              <CButton color="primary" type="submit" disabled={submitting}>
                {submitting ? (
                  <>
                    <CSpinner component="span" size="sm" className="me-2" />
                    Generating PDF...
                  </>
                ) : (
                  'Generate PDF'
                )}
              </CButton>
            </form>
          </CCardBody>
        </CCard>
      </CCol>
    </CRow>
  )
}

export default AlertForms
