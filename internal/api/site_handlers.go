package api

import (
	"net/http"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/metadata"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/gin-gonic/gin"
)

type SiteAPI struct {
	Reg  systemservice.Registry
	Meta *metadata.Store
}

func NewSiteAPI(reg systemservice.Registry, meta *metadata.Store) *SiteAPI {
	return &SiteAPI{Reg: reg, Meta: meta}
}

func (a *SiteAPI) parseSite(c *gin.Context) (string, systemservice.SystemManager, bool) {
	site := strings.ToLower(c.Param("site"))
	mgr, ok := a.Reg.Get(site)
	return site, mgr, ok
}

func (a *SiteAPI) GetMetadata(c *gin.Context) {
	site := strings.ToLower(c.Param("site"))
	cfg, ok := a.Meta.Get(site)
	if !ok {
		c.JSON(http.StatusNotFound, errJSON("NotFound", "unknown site", gin.H{"site": site}))
		return
	}
	c.JSON(http.StatusOK, cfg)
}

func (a *SiteAPI) GetCoverage(c *gin.Context) {
	site, mgr, ok := a.parseSite(c)
	if !ok {
		c.JSON(http.StatusNotFound, errJSON("NotFound", "unknown site", gin.H{"site": site}))
		return
	}
	coverage, err := mgr.Coverage()
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "coverage error", gin.H{"err": err.Error()}))
		return
	}
	c.JSON(http.StatusOK, gin.H{"site": site, "coverage": coverage})
}

func (a *SiteAPI) GetSeries(c *gin.Context) {
	site, mgr, ok := a.parseSite(c)
	if !ok {
		c.JSON(http.StatusNotFound, errJSON("NotFound", "unknown site", gin.H{"site": site}))
		return
	}

	startStr, endStr := c.Query("start"), c.Query("end")
	if startStr == "" || endStr == "" {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "start and end required (RFC3339)", nil))
		return
	}
	start, err1 := time.Parse(time.RFC3339, startStr)
	end, err2 := time.Parse(time.RFC3339, endStr)
	if err1 != nil || err2 != nil || !start.Before(end) {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid start/end", gin.H{"start": startStr, "end": endStr}))
		return
	}

	rows, err := mgr.GetRange(start, end)
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "get range error", gin.H{"err": err.Error()}))
		return
	}

	fields := parseFields(c.Query("fields"))
	includeSoft := parseSoftInclude(c.Query("soft"))

	if includeSoft {
		for i := range rows {
			addSoftSensors(a.Meta, site, rows[i])
		}
	}

	if len(fields) > 0 {
		for i := range rows {
			rows[i] = projectFields(rows[i], strings.Join(fields, ","))
		}
	}

	format := strings.ToLower(c.DefaultQuery("format", "columns"))
	switch format {
	case "rows":
		c.JSON(http.StatusOK, gin.H{"site": site, "data": rows})
		return
	case "columns":
		data := rowsToColumns(rows, fields)
		c.JSON(http.StatusOK, gin.H{"site": site, "data": data})
		return
	default:
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid format", gin.H{"format": format}))
		return
	}
}

func parseFields(s string) []string {
	if s == "" {
		return nil
	}
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		v := strings.TrimSpace(p)
		if v != "" {
			out = append(out, v)
		}
	}
	return out
}

func parseSoftInclude(s string) bool {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "include", "true", "1", "yes":
		return true
	default:
		return false
	}
}

func rowsToColumns(rows []map[string]any, fields []string) map[string]any {
	out := map[string]any{}
	if len(rows) == 0 {
		out["t"] = []int64{}
		out["series"] = map[string][]any{}
		return out
	}

	if len(fields) == 0 {
		for k := range rows[0] {
			if k == "id" {
				continue
			}
			fields = append(fields, k)
		}
	}

	t := make([]int64, 0, len(rows))
	series := map[string][]any{}
	for _, f := range fields {
		if f == "id" {
			continue
		}
		series[f] = make([]any, 0, len(rows))
	}

	for _, row := range rows {
		if v, ok := row["plctime"]; ok {
			if tt, ok := v.(time.Time); ok {
				t = append(t, tt.UTC().UnixMilli())
			} else if ts, ok := v.(string); ok {
				if parsed, err := time.Parse(time.RFC3339, ts); err == nil {
					t = append(t, parsed.UTC().UnixMilli())
				}
			}
		}
		for _, f := range fields {
			if f == "id" {
				continue
			}
			series[f] = append(series[f], row[f])
		}
	}

	out["t"] = t
	out["series"] = series
	return out
}
