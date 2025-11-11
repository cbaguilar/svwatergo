/*
Utility functions that are used by the datamodels package.
*/
package util

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"
)

func ParseStringToBool(s string) bool {
	switch strings.TrimSpace(strings.ToLower(s)) {
	case "1", "t", "true", "y", "yes", "on":
		return true
	}
	return false
}

func ParseStringToInt(s string) int64 {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0
	}
	if i, err := strconv.ParseInt(s, 10, 64); err == nil {
		return i
	}
	// allow floats that are actually ints: "3.0"
	if f, err := strconv.ParseFloat(s, 64); err == nil {
		return int64(f)
	}
	return 0
}

func ParseStringToFloat(s string) float64 {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0
	}
	f, _ := strconv.ParseFloat(s, 64)
	return f
}

var zonedLayouts = []string{
	time.RFC3339Nano, // 2006-01-02T15:04:05.999999999Z07:00
	time.RFC3339,     // 2006-01-02T15:04:05Z07:00
}

var noZoneLayouts = []string{
	"2006-01-02-15:04:05.999999999",
	"2006-01-02-15:04:05.999",
	"2006-01-02-15:04:05",
	"2006-01-02 15:04:05.999999999",
	"2006-01-02 15:04:05.999",
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

// UnmarshalCaseInsensitive lowers all JSON keys before decoding into v.
// v should use lowercase json tags (e.g., json:"totalroflow").
func UnmarshalCaseInsensitive(data []byte, v any, aliases map[string][]string) error {
	// 1) decode into a generic map
	var m map[string]any
	if err := json.Unmarshal(data, &m); err != nil {
		return err
	}

	// 2) normalize keys to lowercase
	lc := make(map[string]any, len(m))
	for k, val := range m {
		lc[strings.ToLower(k)] = val
	}

	// 3) apply alias mapping (e.g., "dailyinletflow" <= ["dailyinletFlow","DailyInletFlow"])
	for canonical, alts := range aliases {
		if _, ok := lc[canonical]; ok {
			continue
		}
		for _, a := range alts {
			if v, ok := lc[strings.ToLower(a)]; ok {
				lc[canonical] = v
				break
			}
		}
	}

	// 4) re-encode and unmarshal into the strongly-typed struct
	buf, err := json.Marshal(lc)
	if err != nil {
		return fmt.Errorf("re-marshal: %w", err)
	}
	dec := json.NewDecoder(bytes.NewReader(buf))
	dec.UseNumber() // optional: preserve number precision
	return dec.Decode(v)
}

func StructToMap(v any) (map[string]any, error) {
	b, err := json.Marshal(v)
	if err != nil {
		return nil, err
	}
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.UseNumber()
	m := make(map[string]any)
	if err := dec.Decode(&m); err != nil {
		return nil, err
	}
	return m, nil
}

func StructsToMaps[T any](items []T) ([]map[string]any, error) {
	out := make([]map[string]any, 0, len(items))
	for _, it := range items {
		m, err := StructToMap(it)
		if err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, nil
}
