package util_test

import (
	"testing"

	"github.com/cbaguilar/svwatergo/internal/util"
)

func TestParseStringToBool(t *testing.T) {
	cases := map[string]bool{
		"1": true, " t ": true, "TRUE": true, "y": true, "Yes": true, "on": true,
		"0": false, "f": false, "no": false, "off": false, "": false, "   ": false,
		" 2 ": false, "maybe": false,
	}
	for in, want := range cases {
		if got := util.ParseStringToBool(in); got != want {
			t.Fatalf("ParseStringToBool(%q) = %v, want %v", in, got, want)
		}
	}
}

func TestParseStringToInt(t *testing.T) {
	type tc struct {
		in   string
		want int64
	}
	tests := []tc{
		{" 42 ", 42},
		{"", 0},
		{"003", 3},
		{"3.0", 3}, // float that is an int
		{"3.9", 3}, // note: current behavior truncates via int64(f)
		{"-7", -7},
		{"abc", 0},      // error -> 0
		{"  -8.0 ", -8}, // float-as-int negative
	}
	for _, tt := range tests {
		if got := util.ParseStringToInt(tt.in); got != tt.want {
			t.Fatalf("ParseStringToInt(%q) = %d, want %d", tt.in, got, tt.want)
		}
	}
}

func TestParseStringToFloat(t *testing.T) {
	type tc struct {
		in   string
		want float64
	}
	tests := []tc{
		{"", 0},
		{" 0 ", 0},
		{"1.25", 1.25},
		{"-2.5", -2.5},
		{"abc", 0}, // error path returns 0
	}
	for _, tt := range tests {
		if got := util.ParseStringToFloat(tt.in); got != tt.want {
			t.Fatalf("ParseStringToFloat(%q) = %v, want %v", tt.in, got, tt.want)
		}
	}
}
