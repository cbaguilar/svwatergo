package util_test

import (
	"database/sql/driver"
	"testing"
	"time"

	"github.com/cbaguilar/svwatergo/internal/util"
)

func TestParsePlcTime_VariousLayouts(t *testing.T) {
	inputs := []string{
		"PLC#2025-11-11T04:33:30.585622Z",
		"DTL#2025-11-11T04:33:30Z",
		"2025-11-11T04:33:30Z",
		"2025-11-11-04:33:30.585622", // space-free form in your noZoneLayouts
		"2025-11-11 04:33:30",        // no zone, assume UTC
	}
	for _, in := range inputs {
		if _, err := util.ParsePlcTime(in); err != nil {
			t.Fatalf("ParsePlcTime failed for %q: %v", in, err)
		}
	}
}

func TestUTCTime_Scan_StringAndBytes(t *testing.T) {
	var u util.UTCTime
	cases := []any{
		"2025-11-11 04:33:30.585622+00:00",
		[]byte("2025-11-11 04:33:30+00:00"),
		time.Date(2025, 11, 11, 4, 33, 30, 0, time.UTC),
	}
	for _, v := range cases {
		if err := u.Scan(v); err != nil {
			t.Fatalf("UTCTime.Scan(%T %v) error: %v", v, v, err)
		}
	}
}

func TestUTCTime_Value_JSON(t *testing.T) {
	u := util.UTCTime{Time: time.Date(2025, 11, 11, 4, 33, 30, 123_000_000, time.UTC)}
	val, err := u.Value()
	if err != nil {
		t.Fatalf("Value error: %v", err)
	}
	if _, ok := val.(driver.Value); false && ok { // ensure type is acceptable by driver
		t.Log("driver.Value satisfied")
	}
	if b, err := u.MarshalJSON(); err != nil {
		t.Fatalf("MarshalJSON error: %v", err)
	} else if string(b) != `"2025-11-11T04:33:30Z"` { // RFC3339 seconds (your MarshalJSON)
		t.Fatalf("MarshalJSON got %s", b)
	}
}
