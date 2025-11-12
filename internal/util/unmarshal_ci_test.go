package util_test

import (
	"encoding/json"
	"log"
	"testing"

	"github.com/cbaguilar/svwatergo/internal/util"
)

type tmp struct {
	DailyInletFlow string `json:"dailyinletflow"`
	Alarm          string `json:"alarm"`
}

// This mostly tests that regardless of the casing of the input JSON keys,
// a raw string-based struct can be populated correctly.
// The final typed struct will be made in a lower layer since it could
// involve parsing and type conversions.
func TestUnmarshalCaseInsensitive_Aliases(t *testing.T) {
	src := map[string]any{
		"DailyInletFlow": "12.5", // camel
		"ALARM":          "1",    // shouting
	}
	raw, _ := json.Marshal(src)

	var got tmp
	aliases := map[string][]string{
		"dailyinletflow": {"DailyInletFlow", "dailyInletFlow"},
	}
	if err := util.UnmarshalCaseInsensitive(raw, &got, aliases); err != nil {
		log.Println("got error:", err)
		log.Println("raw data:", string(raw))

		t.Fatalf("UnmarshalCaseInsensitive error: %v", err)
	}
	if got.DailyInletFlow != "12.5" {
		t.Fatalf("DailyInletFlow got %v", got.DailyInletFlow)
	}
	if got.Alarm != "1" {
		t.Fatalf("Alarm got %v", got.Alarm)
	}
}
