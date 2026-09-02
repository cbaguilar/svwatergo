import React from 'react'

const Dashboard = React.lazy(() => import('./views/dashboard/Dashboard'))
const DetailedDashboard = React.lazy(() => import('./views/detailed-dashboard/DetailedDashboard'))
const UserManagement = React.lazy(() => import('./views/user-management/UserManagement'))
const DataManagement = React.lazy(() => import('./views/data-management/DataManagement'))
const SystemManagement = React.lazy(() => import('./views/system-management/SystemManagement'))
const AlertForms = React.lazy(() => import('./views/alert-forms/AlertForms'))
const AudioInferenceExplorer = React.lazy(
  () => import('./views/audio-inference/AudioInferenceExplorer'),
)
const Documentation = React.lazy(() => import('./views/documentation/Documentation'))
const About = React.lazy(() => import('./views/about/About'))
const FaqContact = React.lazy(() => import('./views/faq/FaqContact'))
const Information = React.lazy(() => import('./views/information/Information'))

const routes = [
  { path: '/', exact: true, name: 'Home' },
  { path: '/dashboard', name: 'Home', element: Dashboard },
  { path: '/detailed-dashboard', name: 'Detailed Dashboard', element: DetailedDashboard },
  { path: '/user-management', name: 'User Management', element: UserManagement },
  { path: '/data-management', name: 'Data Management', element: DataManagement },
  { path: '/system-management', name: 'System Management', element: SystemManagement },
  { path: '/alert-forms', name: 'Alert Forms', element: AlertForms },
  { path: '/audio-inference', name: 'Audio Inference', element: AudioInferenceExplorer },
  { path: '/documentation', name: 'Documentation', element: Documentation },
  { path: '/about', name: 'About SVWaterNet', element: About },
  { path: '/faq', name: 'FAQ & Contact', element: FaqContact },
  { path: '/information', name: 'Information', element: Information },
]

export default routes
