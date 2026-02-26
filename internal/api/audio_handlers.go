package api

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/audio"
	"github.com/gin-gonic/gin"
)

type AudioAPI struct {
	Store *audio.Store
}

type upsertAudioSourceRequest struct {
	Site        string `json:"site"`
	SourceKey   string `json:"source_key"`
	DisplayName string `json:"display_name"`
	Description string `json:"description"`
	IsActive    *bool  `json:"is_active"`
}

type upsertAudioArtifactRequest struct {
	Site        string          `json:"site"`
	SourceKey   string          `json:"source_key"`
	S3Bucket    string          `json:"s3_bucket"`
	S3Key       string          `json:"s3_key"`
	PublicURL   string          `json:"public_url"`
	UTCDay      string          `json:"utc_day"`
	StartTime   string          `json:"start_time"`
	EndTime     string          `json:"end_time"`
	DurationMS  int             `json:"duration_ms"`
	Format      string          `json:"format"`
	ContentType string          `json:"content_type"`
	SizeBytes   *int64          `json:"size_bytes"`
	ETag        string          `json:"etag"`
	Metadata    json.RawMessage `json:"metadata"`
}

func NewAudioAPI(store *audio.Store) *AudioAPI {
	return &AudioAPI{Store: store}
}

func (a *AudioAPI) ListSources(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "audio store not configured", nil))
		return
	}
	sources, err := a.Store.ListAudioSources(c.Request.Context(), audio.ListAudioSources{
		Site: strings.TrimSpace(c.Query("site")),
	})
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "list audio sources failed", gin.H{"err": err.Error()}))
		return
	}
	c.JSON(http.StatusOK, gin.H{"sources": sources})
}

func (a *AudioAPI) UpsertSource(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "audio store not configured", nil))
		return
	}
	var req upsertAudioSourceRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid json", gin.H{"err": err.Error()}))
		return
	}
	if strings.TrimSpace(req.Site) == "" || strings.TrimSpace(req.SourceKey) == "" {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "site and source_key required", nil))
		return
	}

	source, err := a.Store.UpsertAudioSource(c.Request.Context(), audio.UpsertAudioSource{
		Site:        req.Site,
		SourceKey:   req.SourceKey,
		DisplayName: req.DisplayName,
		Description: req.Description,
		IsActive:    req.IsActive,
	})
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "upsert audio source failed", gin.H{"err": err.Error()}))
		return
	}
	c.JSON(http.StatusOK, source)
}

func (a *AudioAPI) ListArtifacts(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "audio store not configured", nil))
		return
	}
	start, err := parseOptionalRFC3339(c.Query("start"))
	if err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid start timestamp", gin.H{"start": c.Query("start")}))
		return
	}
	end, err := parseOptionalRFC3339(c.Query("end"))
	if err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid end timestamp", gin.H{"end": c.Query("end")}))
		return
	}
	limit := parseInt(c.Query("limit"), 0)
	offset := parseInt(c.Query("offset"), 0)
	opts := audio.ListAudioArtifacts{
		Site:      strings.TrimSpace(c.Query("site")),
		SourceKey: strings.TrimSpace(c.Query("source_key")),
		Format:    strings.TrimSpace(c.Query("format")),
		Start:     start,
		End:       end,
		Limit:     limit,
		Offset:    offset,
	}
	items, err := a.Store.ListAudioArtifacts(c.Request.Context(), opts)
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "list audio artifacts failed", gin.H{"err": err.Error()}))
		return
	}
	total, err := a.Store.CountAudioArtifacts(c.Request.Context(), opts)
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "count audio artifacts failed", gin.H{"err": err.Error()}))
		return
	}
	effectiveLimit := limit
	if effectiveLimit <= 0 || effectiveLimit > 200 {
		effectiveLimit = 50
	}
	if offset < 0 {
		offset = 0
	}

	c.JSON(http.StatusOK, gin.H{
		"artifacts": items,
		"paging": gin.H{
			"total":  total,
			"limit":  effectiveLimit,
			"offset": offset,
		},
		"filters": gin.H{
			"site":       strings.TrimSpace(c.Query("site")),
			"source_key": strings.TrimSpace(c.Query("source_key")),
			"format":     strings.TrimSpace(c.Query("format")),
			"start":      strings.TrimSpace(c.Query("start")),
			"end":        strings.TrimSpace(c.Query("end")),
		},
	})
}

func (a *AudioAPI) GetArtifact(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "audio store not configured", nil))
		return
	}
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid id", gin.H{"id": c.Param("id")}))
		return
	}
	item, err := a.Store.GetAudioArtifact(c.Request.Context(), id)
	if err != nil {
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, errJSON("NotFound", "audio artifact not found", gin.H{"id": id}))
			return
		}
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "get audio artifact failed", gin.H{"err": err.Error()}))
		return
	}
	c.JSON(http.StatusOK, item)
}

func (a *AudioAPI) UpsertArtifact(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "audio store not configured", nil))
		return
	}
	var req upsertAudioArtifactRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid json", gin.H{"err": err.Error()}))
		return
	}
	if strings.TrimSpace(req.Site) == "" || strings.TrimSpace(req.SourceKey) == "" || strings.TrimSpace(req.S3Bucket) == "" || strings.TrimSpace(req.S3Key) == "" {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "site, source_key, s3_bucket, and s3_key are required", nil))
		return
	}
	if strings.TrimSpace(req.StartTime) == "" || strings.TrimSpace(req.EndTime) == "" {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "start_time and end_time are required", nil))
		return
	}
	start, err := time.Parse(time.RFC3339, strings.TrimSpace(req.StartTime))
	if err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid start_time (RFC3339)", gin.H{"start_time": req.StartTime}))
		return
	}
	end, err := time.Parse(time.RFC3339, strings.TrimSpace(req.EndTime))
	if err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid end_time (RFC3339)", gin.H{"end_time": req.EndTime}))
		return
	}
	if !end.After(start) {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "end_time must be after start_time", nil))
		return
	}
	var utcDay *time.Time
	if strings.TrimSpace(req.UTCDay) != "" {
		d, err := time.Parse("2006-01-02", strings.TrimSpace(req.UTCDay))
		if err != nil {
			c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid utc_day (YYYY-MM-DD)", gin.H{"utc_day": req.UTCDay}))
			return
		}
		utcDay = &d
	}

	source, err := a.Store.GetAudioSourceBySiteKey(c.Request.Context(), req.Site, req.SourceKey)
	if err != nil {
		if err == sql.ErrNoRows {
			c.JSON(http.StatusBadRequest, errJSON("BadRequest", "audio source does not exist for site/source_key", gin.H{"site": req.Site, "source_key": req.SourceKey}))
			return
		}
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "lookup audio source failed", gin.H{"err": err.Error()}))
		return
	}

	item, err := a.Store.UpsertAudioArtifact(c.Request.Context(), audio.UpsertAudioArtifact{
		Site:        req.Site,
		SourceID:    source.ID,
		S3Bucket:    req.S3Bucket,
		S3Key:       req.S3Key,
		PublicURL:   req.PublicURL,
		UTCDay:      utcDay,
		StartTime:   start,
		EndTime:     end,
		DurationMS:  req.DurationMS,
		Format:      req.Format,
		ContentType: req.ContentType,
		SizeBytes:   req.SizeBytes,
		ETag:        req.ETag,
		Metadata:    req.Metadata,
	})
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "upsert audio artifact failed", gin.H{"err": err.Error()}))
		return
	}
	c.JSON(http.StatusOK, item)
}

func parseOptionalRFC3339(raw string) (*time.Time, error) {
	if strings.TrimSpace(raw) == "" {
		return nil, nil
	}
	t, err := time.Parse(time.RFC3339, strings.TrimSpace(raw))
	if err != nil {
		return nil, err
	}
	return &t, nil
}
