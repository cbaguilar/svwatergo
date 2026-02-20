import React from 'react'
import { useSelector } from 'react-redux'
import { CBadge, CCard, CCardBody, CCardHeader, CCol, CRow } from '@coreui/react'
import SimplifiedROSystem from '../../components/SimplifiedROSystem'

const Dashboard = () => {
  const selectedSystem = useSelector((state) => state.selectedSystem)
  const systemDetails = {
    Bluerock: {
      name: 'Bluerock Water Treatment System',
      description:
        'Live overview of the Bluerock RO facility, highlighting tank levels, treatment flow, and quality metrics.',
    },
    'Santa Teresa': {
      name: 'Santa Teresa Water Treatment System',
      description:
        'Main informational dashboard for the Santa Teresa RO system with real-time storage and quality indicators.',
    },
    'Pryor Farms': {
      name: 'Pryor Farms Water Treatment System',
      description:
        'Operational snapshot of the Pryor Farms treatment system with simplified RO flow and sensor highlights.',
    },
  }
  const currentSystem = systemDetails[selectedSystem] || systemDetails.Bluerock

  return (
    <>
      <CRow className="mb-4">
        <CCol>
          <h2 className="mb-1">Home</h2>
          <div className="text-body-secondary">Basic System Overview</div>
        </CCol>
      </CRow>

      <CRow className="mb-4">
        <CCol>
          <CCard>
            <CCardHeader>System Overview</CCardHeader>
            <CCardBody>
              <h4 className="mb-2">{currentSystem.name}</h4>
              <p className="text-body-secondary mb-0">{currentSystem.description}</p>
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>

      <CRow>
        <CCol lg={7} className="mb-4 mb-lg-0">
          <CCard>
            <CCardHeader>Simplified RO System</CCardHeader>
            <CCardBody>
              <SimplifiedROSystem />
            </CCardBody>
          </CCard>
        </CCol>
        <CCol lg={5}>
          <CCard>
            <CCardHeader>Current State</CCardHeader>
            <CCardBody>
              <div className="text-body-secondary">Current State</div>
              <div className="d-flex align-items-center gap-2 mb-2">
                <span className="fw-semibold">RO Running</span>
                <CBadge color="success">Online</CBadge>
              </div>
              <div className="text-body-secondary mb-4">Last Updated: Feb 20, 2026 2:45:42 AM</div>
              <div className="text-body-secondary mb-2">RO System will remain operational for:</div>
              <div className="d-flex gap-2">
                <div style={{ background: '#0d9488', color: '#fff', borderRadius: 10, padding: '0.5rem 0.75rem', minWidth: 70, textAlign: 'center' }}>
                  <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>0</div>
                  <div style={{ fontSize: '0.7rem', letterSpacing: '0.08em' }}>Days</div>
                </div>
                <div style={{ background: '#0d9488', color: '#fff', borderRadius: 10, padding: '0.5rem 0.75rem', minWidth: 70, textAlign: 'center' }}>
                  <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>0</div>
                  <div style={{ fontSize: '0.7rem', letterSpacing: '0.08em' }}>Hours</div>
                </div>
                <div style={{ background: '#0d9488', color: '#fff', borderRadius: 10, padding: '0.5rem 0.75rem', minWidth: 70, textAlign: 'center' }}>
                  <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>0</div>
                  <div style={{ fontSize: '0.7rem', letterSpacing: '0.08em' }}>Minutes</div>
                </div>
              </div>
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>
    </>
  )
}

export default Dashboard
