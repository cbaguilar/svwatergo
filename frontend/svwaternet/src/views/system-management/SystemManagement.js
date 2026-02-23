import React, { useMemo } from 'react'
import { useSelector } from 'react-redux'
import { CCard, CCardBody, CCardHeader, CCol, CRow } from '@coreui/react'
import OperatorReportsPanel from '../../components/OperatorReportsPanel'

const SystemManagement = () => {
  const selectedSystem = useSelector((state) => state.selectedSystem)
  const siteKey = useMemo(() => {
    switch (selectedSystem) {
      case 'Santa Teresa':
        return 'santateresa'
      case 'Pryor Farms':
        return 'pryorfarm'
      case 'Bluerock':
      default:
        return 'bluerock'
    }
  }, [selectedSystem])

  return (
    <CRow>
      <CCol lg={12}>
        <CCard>
          <CCardHeader>System Management</CCardHeader>
          <CCardBody className="text-body-secondary">
            Administrative tools and operational reporting for the selected site.
          </CCardBody>
        </CCard>
      </CCol>
      <CCol lg={12} className="mt-4">
        <OperatorReportsPanel siteKey={siteKey} />
      </CCol>
    </CRow>
  )
}

export default SystemManagement
