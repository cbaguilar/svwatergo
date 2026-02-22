import React, { useEffect, useMemo, useState } from 'react'
import {
  CAvatar,
  CDropdown,
  CDropdownDivider,
  CDropdownItem,
  CDropdownMenu,
  CDropdownToggle,
} from '@coreui/react'
import { cilUser, cilLockLocked } from '@coreui/icons'
import CIcon from '@coreui/icons-react'

const AppHeaderDropdown = ({ currentUser, onLogout }) => {
  const [avatarReady, setAvatarReady] = useState(false)
  const displayName =
    currentUser?.name?.trim() || currentUser?.email?.trim() || 'Signed In User'
  const pictureUrl = currentUser?.picture?.trim() || ''

  useEffect(() => {
    let active = true
    if (!pictureUrl) {
      setAvatarReady(false)
      return undefined
    }
    const img = new Image()
    img.referrerPolicy = 'no-referrer'
    img.onload = () => {
      if (active) setAvatarReady(true)
    }
    img.onerror = () => {
      if (active) setAvatarReady(false)
    }
    img.src = pictureUrl
    return () => {
      active = false
    }
  }, [pictureUrl])

  return (
    <CDropdown variant="nav-item" className="app-header-user-dropdown">
      <CDropdownToggle placement="bottom-end" className="py-0 pe-0 app-header-user-toggle" caret={false}>
        {avatarReady ? (
          <CAvatar src={pictureUrl} size="sm" />
        ) : (
          <CAvatar size="sm" color="secondary">
            <CIcon icon={cilUser} size="sm" />
          </CAvatar>
        )}
        <span className="ms-2 d-none d-lg-inline app-header-user-name" style={{ textTransform: 'none' }}>
          {displayName}
        </span>
      </CDropdownToggle>
      <CDropdownMenu className="pt-0" placement="bottom-end">
        <CDropdownItem disabled>
          <CIcon icon={cilUser} className="me-2" />
          {currentUser?.email || 'Profile'}
        </CDropdownItem>
        <CDropdownDivider />
        <CDropdownItem
          href="#"
          onClick={(event) => {
            event.preventDefault()
            if (window.google?.accounts?.id?.disableAutoSelect) {
              window.google.accounts.id.disableAutoSelect()
            }
            onLogout?.()
          }}
        >
          <CIcon icon={cilLockLocked} className="me-2" />
          Sign Out
        </CDropdownItem>
      </CDropdownMenu>
    </CDropdown>
  )
}

export default AppHeaderDropdown
