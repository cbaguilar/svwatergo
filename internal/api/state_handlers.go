// internal/api/state_handlers.go
package api

import (
	"encoding/csv"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/metadata"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/gin-gonic/gin"
)

type StateAPI struct {
	Reg  systemservice.Registry
	Meta *metadata.Store
}

func NewStateAPI(reg systemservice.Registry, meta *metadata.Store) *StateAPI {
	return &StateAPI{Reg: reg, Meta: meta}
}

func (a *StateAPI) parseSite(c *gin.Context) (string, systemservice.SystemManager, bool) {
	site := strings.ToLower(c.Param("site"))
	mgr, ok := a.Reg.Get(site)
	return site, mgr, ok
}

func (a *StateAPI) GetLatest(c *gin.Context) {
	site, mgr, ok := a.parseSite(c)
	if !ok {
		c.JSON(http.StatusNotFound, errJSON("NotFound", "unknown site", gin.H{"site": site}))
		return
	}
	data, err := mgr.GetLatest()
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "failed to get latest", gin.H{"err": err.Error()}))
		return
	}

	// Conditional ETag support (weak ETag from site + recordtime + maybe id)
	rt := toRFC3339(data["recordtime"])
	etag := `W/"` + site + ":" + rt + `"`
	if inm := c.GetHeader("If-None-Match"); inm != "" && inm == etag {
		c.Status(http.StatusNotModified)
		return
	}
	c.Header("ETag", etag)
	c.Header("Cache-Control", "private, max-age=5")

	if parseSoftInclude(c.Query("soft")) {
		addSoftSensors(a.Meta, site, data)
	}

	if fields := c.Query("fields"); fields != "" {
		data = projectFields(data, fields)
	}
	c.JSON(http.StatusOK, gin.H{"meta": gin.H{"site": site, "as_of": time.Now().UTC().Format(time.RFC3339), "etag": etag}, "data": data})
}

// Function to write CSV response (called fromm GetRange after we already have rows)
// writeCSVResponse writes rows as CSV to the client using encoding/csv
func writeCSVResponse(c *gin.Context, rows []map[string]interface{}) {
	if len(rows) == 0 {
		c.String(http.StatusOK, "")
		return
	}

	// Collect headers from first row (preserves insertion order if map is ordered upstream)
	var headers []string
	for k := range rows[0] {
		headers = append(headers, k)
	}

	c.Header("Content-Disposition", "attachment; filename=\"data.csv\"")
	c.Header("Content-Type", "text/csv")

	var sb strings.Builder
	writer := csv.NewWriter(&sb)

	// Write header row
	if err := writer.Write(headers); err != nil {
		c.String(http.StatusInternalServerError, "failed to write csv header: %v", err)
		return
	}

	// Write data rows
	for _, row := range rows {
		record := make([]string, len(headers))
		for i, h := range headers {
			if v, ok := row[h]; ok && v != nil {
				record[i] = fmt.Sprintf("%v", v)
			} else {
				record[i] = ""
			}
		}
		if err := writer.Write(record); err != nil {
			c.String(http.StatusInternalServerError, "failed to write csv record: %v", err)
			return
		}
	}

	writer.Flush()
	if err := writer.Error(); err != nil {
		c.String(http.StatusInternalServerError, "csv writer error: %v", err)
		return
	}

	c.String(http.StatusOK, sb.String())
}

func (a *StateAPI) GetRange(c *gin.Context) {
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

	if parseSoftInclude(c.Query("soft")) {
		for i := range rows {
			addSoftSensors(a.Meta, site, rows[i])
		}
	}

	// optional projection
	if fields := c.Query("fields"); fields != "" {
		for i := range rows {
			rows[i] = projectFields(rows[i], fields)
		}
	}

	// if desired output is CSV, set headers and return
	if strings.Contains(c.GetHeader("Accept"), "text/csv") || c.Query("format") == "csv" {
		writeCSVResponse(c, rows)
		return
	}

	// optional smoothing + downsampling
	method := qenum(c.Query("smooth"), "none", []string{"none", "median", "mean", "gauss"})
	window := qint(c.Query("window"), 0)
	sample := qenum(c.Query("sample"), "none", []string{"none", "stride", "bin"})
	maxPts := qint(c.Query("max_points"), 0)

	rows = smooth(rows, method, window)     // implement as no-op if method=="none"
	rows = downsample(rows, sample, maxPts) // no-op if sample=="none" or maxPts==0

	// optional pagination (cursor opaque over last recordtime+id if you keep one)
	cursor := "" // set if you implement server-side pagination
	meta := gin.H{
		"site":       site,
		"start":      start.UTC().Format(time.RFC3339),
		"end":        end.UTC().Format(time.RFC3339),
		"returned":   len(rows),
		"cursor":     cursor,
		"downsample": gin.H{"method": sample, "max_points": maxPts},
		"smooth":     gin.H{"method": method, "window": window},
	}
	c.JSON(http.StatusOK, gin.H{"meta": meta, "data": rows})
}

// helpers

func errJSON(code, msg string, details gin.H) gin.H {
	return gin.H{"error": gin.H{"code": code, "message": msg, "details": details}}
}

func toRFC3339(v any) string {
	switch t := v.(type) {
	case time.Time:
		return t.UTC().Format(time.RFC3339)
	case string:
		return t
	default:
		return ""
	}
}

func projectFields(m map[string]any, fields string) map[string]any {
	set := map[string]struct{}{}
	for _, f := range strings.Split(fields, ",") {
		set[strings.TrimSpace(f)] = struct{}{}
	}
	out := make(map[string]any, len(set))
	for k := range set {
		if v, ok := m[k]; ok {
			out[k] = v
		}
	}
	return out
}

// silly placeholders so this compiles if you stub out
func qint(s string, def int) int {
	if s == "" {
		return def
	}
	return def
}
func qenum(s, def string, allowed []string) string {
	if s == "" {
		return def
	}
	for _, a := range allowed {
		if s == a {
			return s
		}
	}
	return def
}
func smooth(rows []map[string]any, method string, window int) []map[string]any     { return rows }
func downsample(rows []map[string]any, method string, maxPts int) []map[string]any { return rows }
