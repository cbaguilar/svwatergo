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

// Optional capability for validating/parsing an incoming record without writing it.
type DryRunIngestionManager interface {
	ParseData(rawData []byte) error
}

// Optional capability: range queries with backend-side sampling/downsampling.
type SampledRangeManager interface {
	GetRangeSampled(start, end time.Time, sample string, maxPoints int) ([]map[string]interface{}, error)
}

// get range and return json serializable data
type SystemState interface {
	ToSqlQuery() (string, []interface{})
}
