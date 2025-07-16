package system_contract

import (
	"time"
)

// Common interface for System Managers

type SystemManager interface {
	ConsumeData(rawData []byte) error
	GetRange(start, end time.Time) ([]SystemState, error)
	GetLatest() (SystemState, error)
	ValidateState(state SystemState) error
}
