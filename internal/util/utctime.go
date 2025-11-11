// internal/util/utctime.go
package util

import (
	"database/sql/driver"
	"encoding/json"
	"errors"
	"strings"
	"time"
)

type UTCTime struct{ time.Time }

// Known layouts (zoned and non-zoned), including "space + zone" variants.
var timeLayouts = []string{
	// RFC3339 family (with 'T')
	time.RFC3339Nano, // 2006-01-02T15:04:05.999999999Z07:00
	time.RFC3339,     // 2006-01-02T15:04:05Z07:00

	// Space + zone (what you're seeing from SQLite rows)
	"2006-01-02 15:04:05Z07:00",
	"2006-01-02 15:04:05.999Z07:00",
	"2006-01-02 15:04:05.999999Z07:00",
	"2006-01-02 15:04:05.999999999Z07:00",

	// Space, no zone
	"2006-01-02-15:04:05.999999999",
	"2006-01-02-15:04:05.999",
	"2006-01-02-15:04:05",
	"2006-01-02 15:04:05.999999999",
	"2006-01-02 15:04:05.999",
	"2006-01-02 15:04:05",
}

func parseAnyUTC(s string) (time.Time, error) {
	s = strings.TrimSpace(s) // ✅ simplest and cleanest
	for _, layout := range timeLayouts {
		if t, err := time.Parse(layout, s); err == nil {
			return t.UTC(), nil
		}
	}
	return time.Time{}, errors.New("unsupported time " + s)
}

func (t *UTCTime) Scan(src any) error {
	switch v := src.(type) {
	case time.Time:
		t.Time = v.UTC()
		return nil
	case []byte:
		tt, err := parseAnyUTC(string(v))
		if err != nil {
			return err
		}
		t.Time = tt
		return nil
	case string:
		tt, err := parseAnyUTC(v)
		if err != nil {
			return err
		}
		t.Time = tt
		return nil
	case nil:
		t.Time = time.Time{}
		return nil
	default:
		return errors.New("UTCTime: cannot scan type")
	}
}

func (t UTCTime) Value() (driver.Value, error) {
	if t.Time.IsZero() {
		return nil, nil
	}
	return t.Time.UTC().Format(time.RFC3339Nano), nil // store as ISO8601
}

func (t UTCTime) MarshalJSON() ([]byte, error) {
	if t.Time.IsZero() {
		return []byte("null"), nil
	}
	return json.Marshal(t.Time.UTC().Format(time.RFC3339))
}
