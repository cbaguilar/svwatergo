import React from 'react'
import {
  CCard,
  CCardBody,
  CCardHeader,
  CCol,
  CRow,
} from '@coreui/react'

const Dashboard = () => {
  return (
    <>
      <CRow className="mb-4">
        <CCol>
          <h2 className="mb-1">Home</h2>
          <div className="text-body-secondary">Basic System Overview</div>
        </CCol>
      </CRow>

      <CRow className="mb-4">
        <CCol lg={6} className="mb-4 mb-lg-0">
          <CCard>
            <CCardHeader>System Overview</CCardHeader>
            <CCardBody className="text-body-secondary">
              Placeholder for summary details.
            </CCardBody>
          </CCard>
        </CCol>
        <CCol lg={6}>
          <CCard>
            <CCardHeader>Daily Operational Metrics</CCardHeader>
            <CCardBody className="text-body-secondary">
              Placeholder for operational metrics.
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>

      <CRow>
        <CCol>
          <CCard>
            <CCardHeader>Current State</CCardHeader>
            <CCardBody className="text-body-secondary">
              Placeholder for current system status.
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>
    </>
  )
}

export default Dashboard
