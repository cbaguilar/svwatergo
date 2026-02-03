package softsensors

import (
	"errors"
	"strconv"
)

type Calculator func(row map[string]any) (float64, error)

var Registry = map[string]Calculator{
	"ro_recovery": calcRORecovery,
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
	case string:
		f, err := strconv.ParseFloat(t, 64)
		if err != nil {
			return 0, false
		}
		return f, true
	default:
		return 0, false
	}
}
