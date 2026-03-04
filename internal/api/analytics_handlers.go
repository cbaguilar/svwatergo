package api

import (
	"net/http"
	"strings"

	"github.com/cbaguilar/svwatergo/internal/analytics"
	"github.com/cbaguilar/svwatergo/internal/auth"
	"github.com/gin-gonic/gin"
)

type AnalyticsAPI struct {
	Store  *analytics.Store
	Runner *analytics.Runner
}

func NewAnalyticsAPI(store *analytics.Store, runner ...*analytics.Runner) *AnalyticsAPI {
	var selected *analytics.Runner
	if len(runner) > 0 {
		selected = runner[0]
	}
	return &AnalyticsAPI{Store: store, Runner: selected}
}

func (a *AnalyticsAPI) CreateFeatureRun(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "analytics store not configured", nil))
		return
	}
	var req analytics.FeatureRunRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid json", gin.H{"err": err.Error()}))
		return
	}
	req.Site = strings.ToLower(strings.TrimSpace(req.Site))
	if req.Site == "" {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "site required", nil))
		return
	}
	if req.WindowSeconds <= 0 {
		req.WindowSeconds = 60
	}
	if req.MaxGapStaleS <= 0 {
		req.MaxGapStaleS = 300
	}

	createdBy := analyticsCreatedBy(c)
	var (
		job analytics.Job
		err error
	)
	if a.Runner != nil {
		job, err = a.Runner.EnqueueFeature(c.Request.Context(), req, createdBy)
	} else {
		job, err = a.Store.CreateJob(c.Request.Context(), analytics.JobTypeFeatureEngineering, req.Site, createdBy, req)
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "create analytics job failed", gin.H{"err": err.Error()}))
		return
	}
	c.JSON(http.StatusAccepted, gin.H{
		"job":        job,
		"queued":     true,
		"next_step":  "worker execution pending implementation",
		"job_status": "/api/v1/analytics/jobs/" + job.ID,
	})
}

func (a *AnalyticsAPI) CreatePCARun(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "analytics store not configured", nil))
		return
	}
	var req analytics.PCARunRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid json", gin.H{"err": err.Error()}))
		return
	}
	if req.NComponents <= 0 {
		req.NComponents = 8
	}
	if req.InputArtifactID == "" && req.InputURI == "" && req.Site == "" {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "provide input_artifact_id, input_uri, or site/date selection", nil))
		return
	}
	req.Site = strings.ToLower(strings.TrimSpace(req.Site))
	createdBy := analyticsCreatedBy(c)
	var (
		job analytics.Job
		err error
	)
	if a.Runner != nil {
		job, err = a.Runner.EnqueuePCA(c.Request.Context(), req, createdBy)
	} else {
		job, err = a.Store.CreateJob(c.Request.Context(), analytics.JobTypePCA, req.Site, createdBy, req)
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "create analytics job failed", gin.H{"err": err.Error()}))
		return
	}
	c.JSON(http.StatusAccepted, gin.H{
		"job":        job,
		"queued":     true,
		"next_step":  "worker execution pending implementation",
		"job_status": "/api/v1/analytics/jobs/" + job.ID,
	})
}

func (a *AnalyticsAPI) CreateAudioAlignPLCRun(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "analytics store not configured", nil))
		return
	}
	var req analytics.AudioAlignPLCRunRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid json", gin.H{"err": err.Error()}))
		return
	}
	req.Site = strings.ToLower(strings.TrimSpace(req.Site))
	req.Date = strings.TrimSpace(req.Date)
	if req.Site == "" || req.Date == "" {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "site and date are required", nil))
		return
	}
	if strings.TrimSpace(req.AudioBucket) == "" {
		req.AudioBucket = "svwn-audio-files"
	}
	if strings.TrimSpace(req.PLCBucket) == "" {
		req.PLCBucket = "svwaternet"
	}
	if strings.TrimSpace(req.PLCPrefix) == "" {
		req.PLCPrefix = "exports/postgres/plc"
	}
	if strings.TrimSpace(req.AudioPrefix) == "" {
		req.AudioPrefix = "derived/audio-indexed/site=" + req.Site + "/date=" + req.Date + "/"
	}
	if strings.TrimSpace(req.TimestampCol) == "" {
		req.TimestampCol = "plctime"
	}
	if strings.TrimSpace(req.OutS3Prefix) == "" && strings.TrimSpace(req.OutS3Bucket) != "" {
		req.OutS3Prefix = "derived/audio-align"
	}

	createdBy := analyticsCreatedBy(c)
	var (
		job analytics.Job
		err error
	)
	if a.Runner != nil {
		job, err = a.Runner.EnqueueAudioAlignPLC(c.Request.Context(), req, createdBy)
	} else {
		job, err = a.Store.CreateJob(c.Request.Context(), analytics.JobTypeAudioAlignPLC, req.Site, createdBy, req)
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "create analytics job failed", gin.H{"err": err.Error()}))
		return
	}
	c.JSON(http.StatusAccepted, gin.H{
		"job":        job,
		"queued":     true,
		"job_status": "/api/v1/analytics/jobs/" + job.ID,
	})
}

func (a *AnalyticsAPI) GetJob(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "analytics store not configured", nil))
		return
	}
	id := strings.TrimSpace(c.Param("id"))
	if id == "" {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "id required", nil))
		return
	}
	job, ok := a.Store.GetJob(c.Request.Context(), id)
	if !ok {
		c.JSON(http.StatusNotFound, errJSON("NotFound", "analytics job not found", gin.H{"id": id}))
		return
	}
	c.JSON(http.StatusOK, gin.H{"job": job})
}

func (a *AnalyticsAPI) ListJobs(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "analytics store not configured", nil))
		return
	}
	limit := parseInt(c.Query("limit"), 50)
	offset := parseInt(c.Query("offset"), 0)
	jobs := a.Store.ListJobs(c.Request.Context(), limit, offset)
	c.JSON(http.StatusOK, gin.H{
		"jobs": jobs,
		"paging": gin.H{
			"limit":  limit,
			"offset": offset,
		},
	})
}

func analyticsCreatedBy(c *gin.Context) string {
	if id, ok := auth.IdentityFromContext(c.Request.Context()); ok {
		if strings.TrimSpace(id.Email) != "" {
			return id.Email
		}
		return id.Sub
	}
	return ""
}
