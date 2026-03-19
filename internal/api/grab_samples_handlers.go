package api

import (
	"database/sql"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/grabsamples"
	"github.com/gin-gonic/gin"
)

type GrabSamplesAPI struct {
	Store *grabsamples.Store
}

type createGrabSampleRequest struct {
	SampleID        string `json:"sample_id"`
	ExtractedAt     string `json:"extracted_at"`
	ArrivedAt       string `json:"arrived_at"`
	SampleTakenBy   string `json:"sample_taken_by"`
	RawFileName     string `json:"raw_file_name"`
	StorageProvider string `json:"storage_provider"`
	StorageBucket   string `json:"storage_bucket"`
	StorageKey      string `json:"storage_key"`
	FileURL         string `json:"file_url"`
	ParseStatus     string `json:"parse_status"`
	Notes           string `json:"notes"`
}

type updateGrabSampleRequest struct {
	ExtractedAt     *string `json:"extracted_at"`
	ArrivedAt       *string `json:"arrived_at"`
	SampleTakenBy   *string `json:"sample_taken_by"`
	RawFileName     *string `json:"raw_file_name"`
	StorageProvider *string `json:"storage_provider"`
	StorageBucket   *string `json:"storage_bucket"`
	StorageKey      *string `json:"storage_key"`
	FileURL         *string `json:"file_url"`
	ParseStatus     *string `json:"parse_status"`
	Notes           *string `json:"notes"`
}

func NewGrabSamplesAPI(store *grabsamples.Store) *GrabSamplesAPI {
	return &GrabSamplesAPI{Store: store}
}

func (a *GrabSamplesAPI) CreateGrabSample(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "grab samples store not configured", nil))
		return
	}
	var req createGrabSampleRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid json", gin.H{"err": err.Error()}))
		return
	}
	extractedAt, err := parseOptionalTime(req.ExtractedAt)
	if err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid extracted_at", gin.H{"value": req.ExtractedAt}))
		return
	}
	arrivedAt, err := parseOptionalTime(req.ArrivedAt)
	if err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid arrived_at", gin.H{"value": req.ArrivedAt}))
		return
	}
	site := strings.ToLower(strings.TrimSpace(c.Param("site")))
	sample, err := a.Store.CreateGrabSample(c.Request.Context(), grabsamples.CreateGrabSample{
		Site:            site,
		SampleID:        req.SampleID,
		ExtractedAt:     extractedAt,
		ArrivedAt:       arrivedAt,
		SampleTakenBy:   req.SampleTakenBy,
		RawFileName:     req.RawFileName,
		StorageProvider: req.StorageProvider,
		StorageBucket:   req.StorageBucket,
		StorageKey:      req.StorageKey,
		FileURL:         req.FileURL,
		ParseStatus:     req.ParseStatus,
		Notes:           req.Notes,
	})
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "create grab sample failed", gin.H{"err": err.Error()}))
		return
	}
	c.JSON(http.StatusCreated, sample)
}

func (a *GrabSamplesAPI) ListGrabSamples(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "grab samples store not configured", nil))
		return
	}
	site := strings.ToLower(strings.TrimSpace(c.Param("site")))
	limit := parseInt(c.DefaultQuery("limit", ""), 0)
	offset := parseInt(c.DefaultQuery("offset", ""), 0)
	q := strings.TrimSpace(c.Query("q"))

	opts := grabsamples.ListGrabSamples{
		Site:   site,
		Query:  q,
		Limit:  limit,
		Offset: offset,
	}
	items, err := a.Store.ListGrabSamples(c.Request.Context(), opts)
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "list grab samples failed", gin.H{"err": err.Error()}))
		return
	}
	total, err := a.Store.CountGrabSamples(c.Request.Context(), opts)
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "count grab samples failed", gin.H{"err": err.Error()}))
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
		"site":         site,
		"grab_samples": items,
		"paging": gin.H{
			"total":  total,
			"limit":  effectiveLimit,
			"offset": offset,
		},
		"filters": gin.H{
			"q": q,
		},
	})
}

func (a *GrabSamplesAPI) UpdateGrabSample(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "grab samples store not configured", nil))
		return
	}
	site := strings.ToLower(strings.TrimSpace(c.Param("site")))
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid id", gin.H{"id": c.Param("id")}))
		return
	}
	var req updateGrabSampleRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid json", gin.H{"err": err.Error()}))
		return
	}
	extractedAt, err := parseOptionalTimePtr(req.ExtractedAt)
	if err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid extracted_at", gin.H{"value": req.ExtractedAt}))
		return
	}
	arrivedAt, err := parseOptionalTimePtr(req.ArrivedAt)
	if err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid arrived_at", gin.H{"value": req.ArrivedAt}))
		return
	}

	item, err := a.Store.UpdateGrabSample(c.Request.Context(), site, id, grabsamples.UpdateGrabSample{
		ExtractedAt:     extractedAt,
		ArrivedAt:       arrivedAt,
		SampleTakenBy:   req.SampleTakenBy,
		RawFileName:     req.RawFileName,
		StorageProvider: req.StorageProvider,
		StorageBucket:   req.StorageBucket,
		StorageKey:      req.StorageKey,
		FileURL:         req.FileURL,
		ParseStatus:     req.ParseStatus,
		Notes:           req.Notes,
	})
	if err != nil {
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, errJSON("NotFound", "grab sample not found", gin.H{"id": id}))
			return
		}
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "update grab sample failed", gin.H{"err": err.Error()}))
		return
	}
	c.JSON(http.StatusOK, item)
}

func (a *GrabSamplesAPI) DeleteGrabSample(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "grab samples store not configured", nil))
		return
	}
	site := strings.ToLower(strings.TrimSpace(c.Param("site")))
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid id", gin.H{"id": c.Param("id")}))
		return
	}
	if err := a.Store.DeleteGrabSample(c.Request.Context(), site, id); err != nil {
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, errJSON("NotFound", "grab sample not found", gin.H{"id": id}))
			return
		}
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "delete grab sample failed", gin.H{"err": err.Error()}))
		return
	}
	c.Status(http.StatusNoContent)
}

func parseOptionalTime(raw string) (*time.Time, error) {
	value := strings.TrimSpace(raw)
	if value == "" {
		return nil, nil
	}
	t, err := time.Parse(time.RFC3339, value)
	if err != nil {
		return nil, err
	}
	utc := t.UTC()
	return &utc, nil
}

func parseOptionalTimePtr(raw *string) (**time.Time, error) {
	if raw == nil {
		return nil, nil
	}
	parsed, err := parseOptionalTime(*raw)
	if err != nil {
		return nil, err
	}
	return &parsed, nil
}
