import React from 'react'
import { CFooter } from '@coreui/react'

const AppFooter = () => {
  return (
    <CFooter className="px-4">
      <div>
        <span className="fw-semibold">SVWATERNET</span>
        <span className="ms-1">&copy; 2026 UCLA WaTeR Group.</span>
      </div>
      <div className="ms-auto">
        <span className="me-1">A project of the WaTeR group at UCLA.</span>
        <a href="https://cleanwater.seas.ucla.edu/" target="_blank" rel="noopener noreferrer">
          cleanwater.seas.ucla.edu
        </a>
      </div>
    </CFooter>
  )
}

export default React.memo(AppFooter)
