import React, { createContext, useCallback, useContext, useMemo, useState } from 'react'

const HeaderContentContext = createContext({
  headerContent: null,
  setHeaderContent: () => {},
})

export const HeaderContentProvider = ({ children }) => {
  const [headerContent, setHeaderContentState] = useState(null)

  const setHeaderContent = useCallback((content) => {
    setHeaderContentState(content)
  }, [])

  const value = useMemo(
    () => ({
      headerContent,
      setHeaderContent,
    }),
    [headerContent, setHeaderContent],
  )

  return <HeaderContentContext.Provider value={value}>{children}</HeaderContentContext.Provider>
}

export const useHeaderContent = () => useContext(HeaderContentContext)

