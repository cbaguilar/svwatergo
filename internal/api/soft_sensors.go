package api

import (
	"fmt"
	"strconv"

	"github.com/cbaguilar/svwatergo/internal/metadata"
)

func addSoftSensors(meta *metadata.Store, site string, row map[string]any) {
	cfg, ok := meta.Get(site)
	if !ok || len(cfg.SoftSensors) == 0 {
		return
	}

	vars := map[string]float64{}
	for k, v := range row {
		if num, ok := toFloat(v); ok {
			vars[k] = num
		}
	}

	for _, s := range cfg.SoftSensors {
		val, err := metadata.EvalExpr(s.Expr, vars)
		if err != nil {
			continue
		}
		row[s.Key] = val
		vars[s.Key] = val
	}
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
		_ = fmt.Sprintf("%v", v)
		return 0, false
	}
}
