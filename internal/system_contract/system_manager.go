package system_contract

import (
	"time"
)

// Common interface for System Managers

type SystemManager interface {
	SaveData(rawData []byte) error
	// get range and return json serializable data
	GetRange(start, end time.Time) ([]interface{}, error)
	GetLatest() (map[string]interface{}, error)
	ValidateState(state any) error
}
