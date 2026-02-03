package api

import (
	"github.com/cbaguilar/svwatergo/internal/metadata"
	"github.com/cbaguilar/svwatergo/internal/softsensors"
)

func addSoftSensors(meta *metadata.Store, site string, row map[string]any) {
	cfg, ok := meta.Get(site)
	if !ok || len(cfg.SoftSensors) == 0 {
		return
	}

	for _, s := range cfg.SoftSensors {
		calc, ok := softsensors.Registry[s.Key]
		if !ok {
			continue
		}
		val, err := calc(row)
		if err != nil {
			continue
		}
		row[s.Key] = val
	}
}
