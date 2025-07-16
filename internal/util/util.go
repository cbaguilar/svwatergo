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

func ParsePlcTime(s string) (time.Time, error) {
	const layout = time.RFC3339
	parts := strings.Split(s, "#")
	if len(parts) != 2 {
		return time.Time{}, errors.New("invalid time format")
	}
	return time.Parse(layout, parts[1])
}
