import { legacy_createStore as createStore } from 'redux'
import { getBackendKey } from './api/backend'

const initialState = {
  sidebarShow: true,
  theme: 'auto',
  selectedSystem: 'Bluerock',
  apiBackend: getBackendKey(),
}

const changeState = (state = initialState, { type, ...rest }) => {
  switch (type) {
    case 'set':
      return { ...state, ...rest }
    default:
      return state
  }
}

const store = createStore(changeState)
export default store
