import React from 'react'
import { CCard, CCardBody, CCardHeader, CCol, CRow } from '@coreui/react'

const Information = () => {
  return (
    <CRow>
      <CCol>
        <CCard>
          <CCardHeader>Information</CCardHeader>
          <CCardBody className="text-body-secondary">
            Placeholder content for Information.
          </CCardBody>
        </CCard>
      </CCol>
    </CRow>
  )
}

export default Information
