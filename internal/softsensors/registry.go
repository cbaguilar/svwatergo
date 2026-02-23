package softsensors

import (
	"encoding/json"
	"errors"
	"math"
	"strconv"
	"strings"
)

type Calculator func(row map[string]any) (float64, error)

var Registry = map[string]Calculator{
	"ro_recovery":   calcRORecovery,
	"feedflow_soft": calcFeedFlowSoft,
}

func calcRORecovery(row map[string]any) (float64, error) {
	permeate, ok := toFloat(row["permeateflow"])
	if !ok {
		return 0, errors.New("missing permeateflow")
	}
	feed, ok := toFloat(row["feedflow"])
	if !ok || feed == 0 {
		return 0, errors.New("missing feedflow")
	}
	return (permeate / feed) * 100.0, nil
}

func calcFeedFlowSoft(row map[string]any) (float64, error) {
	// FTF (feed flow) is estimated as FT0 - FTR when a direct feedflow sensor is unavailable.
	inlet, ok := toFloat(row["inletflow"])
	if !ok {
		return 0, errors.New("missing inletflow")
	}
	recycle, ok := toFloat(row["recycleflow"])
	if !ok {
		return 0, errors.New("missing recycleflow")
	}
	feed := inlet - recycle
	// Clamp tiny negatives from sensor noise/rounding.
	if feed < 0 && math.Abs(feed) < 0.05 {
		feed = 0
	}
	if feed < 0 {
		return 0, errors.New("computed negative feed flow")
	}
	return feed, nil
}

func toFloat(v any) (float64, bool) {
	switch t := v.(type) {
	case float64:
		return t, true
	case float32:
		return float64(t), true
	case int:
		return float64(t), true
	case int64:
		return float64(t), true
	case int32:
		return float64(t), true
	case uint:
		return float64(t), true
	case uint64:
		return float64(t), true
	case uint32:
		return float64(t), true
	case bool:
		if t {
			return 1, true
		}
		return 0, true
	case json.Number:
		f, err := t.Float64()
		if err != nil || math.IsNaN(f) || math.IsInf(f, 0) {
			return 0, false
		}
		return f, true
	case string:
		f, err := strconv.ParseFloat(strings.TrimSpace(t), 64)
		if err != nil || math.IsNaN(f) || math.IsInf(f, 0) {
			return 0, false
		}
		return f, true
	default:
		return 0, false
	}
}
