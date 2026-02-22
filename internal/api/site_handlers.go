package api

import (
	"net/http"
	"sort"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/metadata"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/cbaguilar/svwatergo/internal/util"
	"github.com/gin-gonic/gin"
)

type SiteAPI struct {
	Reg  systemservice.Registry
	Meta *metadata.Store
}

const powerMeterTickKWh = 1.25 / 1000.0

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
	if parseSoftInclude(c.Query("soft")) {
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

func (a *SiteAPI) GetDailySummary(c *gin.Context) {
	site, mgr, ok := a.parseSite(c)
	if !ok {
		c.JSON(http.StatusNotFound, errJSON("NotFound", "unknown site", gin.H{"site": site}))
		return
	}

	loc, err := time.LoadLocation("America/Los_Angeles")
	if err != nil {
		loc = time.FixedZone("PST", -8*3600)
	}
	nowUTC := time.Now().UTC()
	nowPT := nowUTC.In(loc)
	startPT := time.Date(nowPT.Year(), nowPT.Month(), nowPT.Day(), 0, 0, 0, 0, loc)
	startUTC := startPT.UTC()

	// Include a small lookback so we can use the latest sample before midnight when available.
	lookbackStart := startUTC.Add(-15 * time.Minute)
	rows, err := mgr.GetRange(lookbackStart, nowUTC)
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "get range error", gin.H{"err": err.Error()}))
		return
	}
	if len(rows) == 0 {
		c.JSON(http.StatusOK, gin.H{
			"meta": gin.H{
				"site":              site,
				"timezone":          "America/Los_Angeles",
				"day_start_pacific": startPT.Format(time.RFC3339),
				"as_of":             nowUTC.Format(time.RFC3339),
			},
			"data": gin.H{
				"feed_gallons":                  nil,
				"permeate_gallons":              nil,
				"energy_kwh":                    nil,
				"specific_energy_kwh_per_1000g": nil,
				"estimated_cost_per_1000g_usd":  nil,
			},
		})
		return
	}

	sort.Slice(rows, func(i, j int) bool {
		return rowTimestamp(rows[i]).Before(rowTimestamp(rows[j]))
	})

	latest, err := mgr.GetLatest()
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "failed to get latest", gin.H{"err": err.Error()}))
		return
	}

	baseline := pickDailyBaseline(rows, startUTC)
	current := latest
	if rowTimestamp(current).Before(startUTC) {
		current = rows[len(rows)-1]
	}

	feedDelta, feedField := deltaFromTotalizers(baseline, current, "totalfeedflow", "totalinletflow")
	permDelta, permField := deltaFromTotalizers(baseline, current, "totalroflow")
	energyTicksDelta, energyField := deltaFromTotalizers(baseline, current, "powermeter")
	energyKWh := -1.0
	if energyTicksDelta >= 0 {
		energyKWh = energyTicksDelta * powerMeterTickKWh
	}

	var specificEnergy any = nil
	if permDelta > 0 && energyKWh >= 0 {
		specificEnergy = util.Round2((energyKWh / permDelta) * 1000)
	}

	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{
			"site":                  site,
			"timezone":              "America/Los_Angeles",
			"day_start_pacific":     startPT.Format(time.RFC3339),
			"day_start_utc":         startUTC.Format(time.RFC3339),
			"as_of":                 nowUTC.Format(time.RFC3339),
			"baseline_row_time_utc": rowTimestamp(baseline).UTC().Format(time.RFC3339),
			"current_row_time_utc":  rowTimestamp(current).UTC().Format(time.RFC3339),
			"computed_from": gin.H{
				"feed_totalizer":     feedField,
				"permeate_totalizer": permField,
				"energy_totalizer":   energyField,
			},
		},
		"data": gin.H{
			"feed_gallons":                  nullableNumber(feedDelta),
			"permeate_gallons":              nullableNumber(permDelta),
			"energy_kwh":                    nullableNumber(energyKWh),
			"specific_energy_kwh_per_1000g": specificEnergy,
			"estimated_cost_per_1000g_usd":  nil, // external utility API integration TBD
		},
	})
}

func rowTimestamp(row map[string]any) time.Time {
	if row == nil {
		return time.Time{}
	}
	if v, ok := row["plctime"]; ok {
		if t, ok := util.CoerceUTCTime(v); ok {
			return t
		}
	}
	if v, ok := row["recordtime"]; ok {
		if t, ok := util.CoerceUTCTime(v); ok {
			return t
		}
	}
	return time.Time{}
}

func pickDailyBaseline(rows []map[string]any, startUTC time.Time) map[string]any {
	if len(rows) == 0 {
		return nil
	}
	var lastBefore map[string]any
	var firstAfter map[string]any
	for _, row := range rows {
		ts := rowTimestamp(row)
		if ts.IsZero() {
			continue
		}
		if !ts.After(startUTC) {
			lastBefore = row
			continue
		}
		if firstAfter == nil {
			firstAfter = row
		}
	}
	if lastBefore != nil {
		return lastBefore
	}
	return firstAfter
}

func deltaFromTotalizers(startRow, endRow map[string]any, keys ...string) (float64, string) {
	if startRow == nil || endRow == nil {
		return -1, ""
	}
	for _, key := range keys {
		startV, ok1 := util.NumberFromAny(startRow[key])
		endV, ok2 := util.NumberFromAny(endRow[key])
		if !ok1 || !ok2 {
			continue
		}
		delta := endV - startV
		if delta < 0 {
			return -1, key
		}
		return delta, key
	}
	if len(keys) == 0 {
		return -1, ""
	}
	return -1, keys[0]
}

func nullableNumber(v float64) any {
	if v < 0 {
		return nil
	}
	return util.Round2(v)
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
