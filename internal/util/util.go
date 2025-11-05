/*
Utility functions that are used by the datamodels package.
*/
package util

import (
	"errors"
	"strconv"
	"strings"
	"time"
)

func ParseStringToBool(s string) bool {
	return s == "1"
}

func ParseStringToInt(s string) int64 {
	v, _ := strconv.ParseInt(s, 10, 64)
	return v
}

func ParseStringToFloat(s string) float64 {
	v, _ := strconv.ParseFloat(s, 64)
	return v
}


var zonedLayouts = []string{
	time.RFC3339Nano, // 2006-01-02T15:04:05.999999999Z07:00
	time.RFC3339,     // 2006-01-02T15:04:05Z07:00
}
var noZoneLayouts = []string{
	"2006-01-02-15:04:05.999999999", // 2025-11-05-03:12:41.652946
	"2006-01-02-15:04:05",
	"2006-01-02 15:04:05.999999999",
	"2006-01-02 15:04:05",
}

func ParsePlcTime(s string) (time.Time, error) {
	if s == "" {
		return time.Time{}, errors.New("empty time")
	}
	// Allow PLC#, DTL#, etc.
	if i := strings.IndexByte(s, '#'); i >= 0 {
		s = s[i+1:]
	}
	s = strings.TrimSpace(s)

	for _, layout := range zonedLayouts {
		if t, err := time.Parse(layout, s); err == nil {
			return t.UTC(), nil
		}
	}
	for _, layout := range noZoneLayouts {
		if t, err := time.ParseInLocation(layout, s, time.UTC); err == nil {
			return t.UTC(), nil
		}
	}
	return time.Time{}, errors.New("unsupported time format: " + s)
}

