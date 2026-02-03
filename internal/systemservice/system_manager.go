package systemservice

import (
	"time"
)

// Common interface for System Managers

type SystemManager interface {
	SaveData(rawData []byte) error
	GetRange(start, end time.Time) ([]map[string]interface{}, error)
	GetLatest() (map[string]interface{}, error)
	Coverage() (Coverage, error)
}

// get range and return json serializable data
type SystemState interface {
	ToSqlQuery() (string, []interface{})
}
