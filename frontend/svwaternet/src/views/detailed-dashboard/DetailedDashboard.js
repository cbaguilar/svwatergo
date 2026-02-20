import React from 'react'
import { useSelector } from 'react-redux'
import {
  CBadge,
  CCard,
  CCardBody,
  CCardHeader,
  CCol,
  CFormCheck,
  CFormInput,
  CFormLabel,
  CRow,
} from '@coreui/react'

import BluerockSchematic from '../../components/detailed/BluerockSchematic'
import SantaTeresaPryorFarmsSchematic from '../../components/detailed/SantaTeresaPryorFarmsSchematic'
import PryorFarmsSchematic from '../../components/detailed/PryorFarmsSchematic'

const buildMockMd = () => {
  return {
    get: (key, field) => {
      if (field === 'abbreviated_name') return key?.slice(0, 3)?.toUpperCase() || ''
      if (field === 'units') return ''
      if (field === 'current_value') return 0
      if (field === 'on_click') return () => {}
      return ''
    },
  }
}

const DetailedDashboard = () => {
  const selectedSystem = useSelector((state) => state.selectedSystem)
  const md = buildMockMd()
  const Schematic =
    selectedSystem === 'Bluerock'
      ? BluerockSchematic
      : selectedSystem === 'Pryor Farms'
        ? PryorFarmsSchematic
        : SantaTeresaPryorFarmsSchematic

  return (
    <>
      <CRow className="mb-4">
        <CCol>
          <h2 className="mb-1">Dashboard</h2>
          <div className="text-body-secondary">Basic System Overview</div>
        </CCol>
      </CRow>

      <CRow className="mb-4">
        <CCol lg={8} className="mb-4 mb-lg-0">
          <CCard className="detailed-schematic-card">
            <CCardHeader>Detailed Process Flow</CCardHeader>
            <CCardBody className="detailed-schematic-body">
              <div className="w-100" style={{ height: 500 }}>
                <Schematic md={md} />
              </div>
            </CCardBody>
          </CCard>
        </CCol>
        <CCol lg={4}>
          <CCard>
            <CCardHeader>Date Selection</CCardHeader>
            <CCardBody>
              <CFormCheck id="liveData" label="Live Data" defaultChecked className="mb-3" />
              <CFormLabel htmlFor="datePicker" className="small text-body-secondary">
                Date
              </CFormLabel>
              <CFormInput id="datePicker" type="date" />
            </CCardBody>
          </CCard>
          <CCard className="mt-4">
            <CCardHeader>Sensor Status</CCardHeader>
            <CCardBody>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>RO Status</span>
                <CBadge color="warning">RO Standby</CBadge>
              </div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>Well Pump</span>
                <CBadge color="danger">Not Running</CBadge>
              </div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>P1 Feed Pump</span>
                <CBadge color="danger">Not Running</CBadge>
              </div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>AV1 Inlet Valve</span>
                <CBadge color="danger">Closed</CBadge>
              </div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>P2 RO Pump</span>
                <CBadge color="danger">Not Running</CBadge>
              </div>
              <div className="d-flex justify-content-between align-items-center mb-2">
                <span>AV6 Product Diversion Valve</span>
                <CBadge color="danger">Divert to Residual Line</CBadge>
              </div>
              <div className="d-flex justify-content-between align-items-center">
                <span>P3 Delivery Pump</span>
                <CBadge color="danger">Not Running</CBadge>
              </div>
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>

      <CRow>
        <CCol>
          <CCard>
            <CCardHeader>Current Warnings</CCardHeader>
            <CCardBody className="text-body-secondary">
              <ul className="mb-0">
                <li>Residual Diversion Disabled</li>
                <li>Residual Tank Sensor Error</li>
              </ul>
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>
    </>
  )
}

export default DetailedDashboard
