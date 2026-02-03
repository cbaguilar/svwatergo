package systemservice

import "time"

type Coverage struct {
	MinPlcTime    *time.Time `db:"min_plctime" json:"min_plctime,omitempty"`
	MaxPlcTime    *time.Time `db:"max_plctime" json:"max_plctime,omitempty"`
	MaxRecordTime *time.Time `db:"max_recordtime" json:"max_recordtime,omitempty"`
	Count         int64      `db:"count" json:"count"`
}
