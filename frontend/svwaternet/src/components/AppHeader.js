import React, { useEffect, useRef } from 'react'
import { useSelector, useDispatch } from 'react-redux'
import {
  CContainer,
  CFormSelect,
  CHeader,
  CHeaderNav,
  CHeaderToggler,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilMenu } from '@coreui/icons'
import { BACKEND_OPTIONS, setBackendKey } from '../api/backend'
import { useHeaderContent } from './header/HeaderContentContext'

import { AppBreadcrumb } from './index'
import { AppHeaderDropdown } from './header/index'

const AppHeader = () => {
  const headerRef = useRef()

  const dispatch = useDispatch()
  const sidebarShow = useSelector((state) => state.sidebarShow)
  const selectedSystem = useSelector((state) => state.selectedSystem)
  const apiBackend = useSelector((state) => state.apiBackend)
  const { headerContent } = useHeaderContent()

  useEffect(() => {
    const handleScroll = () => {
      headerRef.current &&
        headerRef.current.classList.toggle('shadow-sm', document.documentElement.scrollTop > 0)
    }

    document.addEventListener('scroll', handleScroll)
    return () => document.removeEventListener('scroll', handleScroll)
  }, [])

  return (
    <CHeader position="sticky" className="mb-4 p-0" ref={headerRef}>
      <CContainer className="border-bottom px-4 app-header-bar" fluid>
        <CHeaderToggler
          onClick={() => dispatch({ type: 'set', sidebarShow: !sidebarShow })}
          style={{ marginInlineStart: '-14px' }}
        >
          <CIcon icon={cilMenu} size="lg" />
        </CHeaderToggler>
        <CHeaderNav className="app-header-title">
          <div className="fw-semibold">WaTeR System</div>
        </CHeaderNav>
        {headerContent && (
          <div className="d-none d-xl-flex align-items-center flex-grow-1 mx-3 app-header-slot">{headerContent}</div>
        )}
        <CHeaderNav className="align-items-center ms-auto app-header-controls">
          <span className="me-2 small text-body-secondary app-header-label">WaTeR System ID:</span>
          <CFormSelect
            size="sm"
            className="me-3 app-header-select"
            aria-label="Water System ID"
            value={selectedSystem}
            onChange={(event) => {
              dispatch({ type: 'set', selectedSystem: event.target.value })
            }}
          >
            <option value="Bluerock">Bluerock</option>
            <option value="Santa Teresa">Santa Teresa</option>
            <option value="Pryor Farms">Pryor Farms</option>
          </CFormSelect>
          <span className="me-2 small text-body-secondary app-header-label">Backend:</span>
          <CFormSelect
            size="sm"
            className="me-3 app-header-select"
            aria-label="API backend target"
            value={apiBackend}
            onChange={(event) => {
              const value = event.target.value
              setBackendKey(value)
              dispatch({ type: 'set', apiBackend: value })
              window.location.reload()
            }}
          >
            {BACKEND_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </CFormSelect>
          <AppHeaderDropdown />
        </CHeaderNav>
      </CContainer>
      <CContainer className="px-4" fluid>
        <AppBreadcrumb />
      </CContainer>
    </CHeader>
  )
}

export default AppHeader
