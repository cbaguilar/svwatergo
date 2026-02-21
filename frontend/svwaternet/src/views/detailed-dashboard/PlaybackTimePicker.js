import React from 'react'
import CIcon from '@coreui/icons-react'
import { cilMediaPause, cilMediaPlay, cilMediaStepBackward, cilMediaStepForward } from '@coreui/icons'
import {
  CBadge,
  CButton,
  CCard,
  CCardBody,
  CCol,
  CDropdown,
  CDropdownItem,
  CDropdownMenu,
  CDropdownToggle,
  CFormInput,
  CRow,
  CSpinner,
} from '@coreui/react'

const PlaybackTimePicker = ({
  isLivePlaying,
  focusedTs,
  streamState,
  activeRangeLabel,
  activeRangeKind,
  timePreset,
  presets,
  isRangeLoading,
  onSelectPreset,
  rangeStartInput,
  rangeEndInput,
  onRangeStartChange,
  onRangeEndChange,
  onApplyCustomRange,
  onTogglePlay,
  onStepBackInterval,
  onStepForwardInterval,
  canStepForward,
}) => {
  const statusLabel = focusedTs ? 'FOCUSED' : isLivePlaying ? 'LIVE' : 'PAUSED'
  const statusColor = focusedTs ? 'warning' : isLivePlaying ? 'success' : 'secondary'

  const streamBadge =
    streamState === 'connected' ? (
      <CBadge color="success">Connected</CBadge>
    ) : streamState === 'reconnecting' || streamState === 'connecting' ? (
      <CBadge color="warning">Reconnecting...</CBadge>
    ) : (
      <CBadge color="secondary">Disconnected</CBadge>
    )

  return (
    <CRow className="mb-3">
      <CCol>
        <CCard>
          <CCardBody style={{ paddingTop: '0.75rem', paddingBottom: '0.75rem' }}>
            <div className="d-flex flex-wrap align-items-center gap-2">
              <CDropdown>
                <CDropdownToggle color="light" size="sm" className="text-start" style={{ minWidth: 220 }}>
                  {activeRangeKind === 'preset' ? presets[timePreset]?.label || activeRangeLabel : activeRangeLabel}
                </CDropdownToggle>
                <CDropdownMenu style={{ minWidth: 320 }}>
                  {Object.entries(presets).map(([value, cfg]) => (
                    <CDropdownItem
                      key={value}
                      active={timePreset === value}
                      onClick={() => onSelectPreset(value)}
                    >
                      {cfg.label}
                    </CDropdownItem>
                  ))}
                  <div className="dropdown-divider" />
                  <div className="px-3 py-2">
                    <div className="small text-body-secondary mb-1">Start</div>
                    <CFormInput
                      size="sm"
                      type="datetime-local"
                      value={rangeStartInput}
                      onChange={(e) => onRangeStartChange(e.target.value)}
                    />
                    <div className="small text-body-secondary mb-1 mt-2">End</div>
                    <CFormInput
                      size="sm"
                      type="datetime-local"
                      value={rangeEndInput}
                      onChange={(e) => onRangeEndChange(e.target.value)}
                    />
                    <CButton color="secondary" variant="outline" size="sm" className="mt-2 w-100" onClick={onApplyCustomRange}>
                      Apply Range
                    </CButton>
                  </div>
                </CDropdownMenu>
              </CDropdown>

              <div className="d-flex align-items-center">
                <CButton
                  color="secondary"
                  variant="outline"
                  size="sm"
                  onClick={onStepBackInterval}
                  aria-label="Step backward one interval"
                  title="Step backward"
                >
                  <CIcon icon={cilMediaStepBackward} />
                </CButton>
                <CButton
                  color={isLivePlaying ? 'primary' : 'secondary'}
                  variant={isLivePlaying ? undefined : 'outline'}
                  size="sm"
                  className="mx-1"
                  onClick={onTogglePlay}
                  aria-label={isLivePlaying ? 'Pause playback' : 'Play live'}
                  title={isLivePlaying ? 'Pause' : 'Play'}
                >
                  <CIcon icon={isLivePlaying ? cilMediaPause : cilMediaPlay} />
                </CButton>
                <CButton
                  color="secondary"
                  variant="outline"
                  size="sm"
                  onClick={onStepForwardInterval}
                  disabled={!canStepForward}
                  aria-label="Step forward one interval"
                  title="Step forward"
                >
                  <CIcon icon={cilMediaStepForward} />
                </CButton>
              </div>

              <CBadge color={statusColor}>{statusLabel}</CBadge>
              {isRangeLoading && (
                <CBadge color="info" className="d-inline-flex align-items-center">
                  <CSpinner size="sm" className="me-1" />
                  Loading
                </CBadge>
              )}
              {streamBadge}
              <div className="small text-body-secondary ms-auto">{activeRangeLabel} (UTC)</div>
            </div>
          </CCardBody>
        </CCard>
      </CCol>
    </CRow>
  )
}

export default PlaybackTimePicker
