import React from 'react'
import { AppContent, AppSidebar, AppFooter, AppHeader } from '../components/index'
import { HeaderContentProvider } from '../components/header/HeaderContentContext'

const DefaultLayout = () => {
  return (
    <HeaderContentProvider>
      <div>
        <AppSidebar />
        <div className="wrapper d-flex flex-column min-vh-100">
          <AppHeader />
          <div className="body flex-grow-1">
            <AppContent />
          </div>
          <AppFooter />
        </div>
      </div>
    </HeaderContentProvider>
  )
}

export default DefaultLayout
