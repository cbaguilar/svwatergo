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

const projectInformation = [
  {
    title:
      'On the Feasibility of Small Communities Wellhead Treatment for Nitrate Removal and Salinity Reduction',
    href: 'https://drive.google.com/file/d/1ai9sL2crnDSsrt3plumkKzeu2ayXbjza/view',
  },
  {
    title: 'Operations and maintenance of Water Treatment System',
    href: 'https://drive.google.com/file/d/1-N3gRMoyGPawG4TzqypwK86Eq0MnsCuW/view',
  },
  {
    title: 'Blue Rock Apartments Water Quality Baseline (Pre-Commissioning)',
    href: 'https://drive.google.com/file/d/1NhKS3roVyp-pTLqZmNoN3nERQpZwJKYN/view',
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
    title: 'Contacts',
    href: 'https://drive.google.com/file/d/1MadJ8mXFMEQlRPqPY7NOJn6dYiGwexML/view?usp=drive_web',
  },
]

const About = () => {
  return (
    <CRow>
      <CCol xs={12} lg={10} xxl={8}>
        <CCard>
          <CCardHeader>About SVWaterNet</CCardHeader>
          <CCardBody>
            <h6 className="mb-3">Information about this project:</h6>
            <CListGroup flush>
              {projectInformation.map((document) => (
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

export default About
