import React from 'react'
import {
  CCard,
  CCardBody,
  CCardHeader,
  CCol,
  CLink,
  CListGroup,
  CListGroupItem,
  CRow,
} from '@coreui/react'

const documents = [
  {
    title: 'Example Alert',
    href: 'https://svwaternet.org/assets/pdf/output.pdf',
  },
  {
    title: 'Alert Form Template',
    href: 'https://svwaternet.org/assets/docx/allalerts.docx',
  },
  {
    title:
      'On the Feasibility of Small Communities Welhead Treatment for Nitrate Removal and Salinity Reduction',
    href: 'https://drive.google.com/file/d/1ai9sL2crnDSsrt3plumkKzeu2ayXbjza/view',
  },
  {
    title: 'Operations and maintenance of Water Treatment System',
    href: 'https://drive.google.com/file/d/1-N3gRMoyGPawG4TzqypwK86Eq0MnsCuW/view',
  },
  {
    title:
      'Emergency Bypass Instructions (Transition from Water Treatment to Direct Well Water Utilization)',
    href: 'https://drive.google.com/file/d/1-xB6jOjeEMwGAno58klJaRiSqDCXRIdq/view',
  },
  {
    title: 'Blue Rock Apartments Water Quality Baseline (Pre-Commissioning)',
    href: 'https://drive.google.com/file/d/1NhKS3roVyp-pTLqZmNoN3nERQpZwJKYN/view',
  },
  {
    title: 'Blue Rock Apartments Baseline Water Quality Monitoring (MBAS Lab Report)',
    href: 'https://drive.google.com/file/d/1KrEGOZOoTVZfPTCJosujOrGe3w7GKvpi/view?usp=drive_web',
  },
  {
    title: 'Blue Rock Apartments Water Treatment Project (Progress through January 2020)',
    href: 'https://drive.google.com/file/d/1pO73v-IKer3trrDCkgjT6rcrwQHph0da/view?usp=drive_web',
  },
  {
    title: 'Blue Rock Apartments Water Treatment System (Panoramic Photo)',
    href: 'https://drive.google.com/file/d/1k4QS--hEzJ7LpB7qvajvL-G0mY2jeq0h/view?usp=drive_web',
  },
  {
    title: 'Blue Rock Apartments Commissioning Letter CMHD - May 8, 2020',
    href: 'https://drive.google.com/file/d/1AdXrDTPDwm9LU2DgVZC1hCpG-QlP8Ijk/view?usp=drive_web',
  },
  {
    title: 'Notices Regarding Water System',
    href: 'https://drive.google.com/file/d/1kVtcYaLSRAW9n8ZvLxnQfMlc5A2f8u4A/view?usp=drive_web',
  },
  {
    title: 'Contacts',
    href: 'https://drive.google.com/file/d/1MadJ8mXFMEQlRPqPY7NOJn6dYiGwexML/view?usp=drive_web',
  },
  {
    title: 'Solicitation of contact information from residents (Spanish)',
    href: 'https://drive.google.com/file/d/1WnkkLVZQltUWFrOLc3yWuROb48qqCN3j/view?usp=drive_web',
  },
  {
    title: 'Solicitation of contact information from residents (English)',
    href: 'https://drive.google.com/file/d/1-zsOnlApm4hJOiaaPBvyjpi6CWlGLUu-/view?usp=drive_web',
  },
]

const Documentation = () => {
  return (
    <CRow>
      <CCol xs={12} lg={10} xxl={8}>
        <CCard>
          <CCardHeader>WaTeR Documentation</CCardHeader>
          <CCardBody>
            <h6 className="mb-3">Selected Public Documents</h6>
            <CListGroup flush>
              {documents.map((document) => (
                <CListGroupItem key={document.href}>
                  <CLink href={document.href} target="_blank" rel="noopener noreferrer">
                    {document.title}
                  </CLink>
                </CListGroupItem>
              ))}
            </CListGroup>
          </CCardBody>
        </CCard>
      </CCol>
    </CRow>
  )
}

export default Documentation
