package api

import (
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/analytics"
	"github.com/cbaguilar/svwatergo/internal/auth"
	"github.com/gin-gonic/gin"
)

type AnalyticsAPI struct {
	Store  *analytics.Store
	Runner *analytics.Runner
}

func NewAnalyticsAPI(store *analytics.Store, runner *analytics.Runner) *AnalyticsAPI {
	return &AnalyticsAPI{Store: store, Runner: runner}
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
	job, err := a.Store.CreateJob(c.Request.Context(), analytics.JobTypeFeatureEngineering, req.Site, createdBy, req)
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
	job, err := a.Store.CreateJob(c.Request.Context(), analytics.JobTypePCA, req.Site, createdBy, req)
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

func (a *AnalyticsAPI) CreateAudioInferenceRun(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "analytics store not configured", nil))
		return
	}
	var req analytics.AudioInferenceRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid json", gin.H{"err": err.Error()}))
		return
	}
	req.Normalize()
	if err := req.Validate(); err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid audio inference request", gin.H{"err": err.Error()}))
		return
	}
	createdBy := analyticsCreatedBy(c)
	var (
		job analytics.Job
		err error
	)
	if a.Runner != nil {
		job, err = a.Runner.EnqueueAudioInference(c.Request.Context(), req, createdBy)
	} else {
		job, err = a.Store.CreateJob(c.Request.Context(), analytics.JobTypeAudioInference, req.Site, createdBy, req)
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "create analytics job failed", gin.H{"err": err.Error()}))
		return
	}
	c.JSON(http.StatusAccepted, gin.H{
		"job":        job,
		"queued":     true,
		"next_step":  "poll job_status until completed",
		"job_status": "/api/v1/analytics/jobs/" + job.ID,
	})
}

func (a *AnalyticsAPI) CreateAudioInferenceStage(c *gin.Context) {
	stageRoot := strings.TrimSpace(os.Getenv("ANALYTICS_AUDIO_STAGE_ROOT"))
	if stageRoot == "" {
		stageRoot = filepath.Join("data", "analytics", "staging")
	}
	if err := os.MkdirAll(stageRoot, 0o755); err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "failed to prepare staging dir", gin.H{"err": err.Error()}))
		return
	}

	// Multipart upload path.
	fh, err := c.FormFile("file")
	if err == nil && fh != nil {
		safeName := sanitizeStageFilename(fh.Filename)
		stageName := time.Now().UTC().Format("20060102T150405.000000000Z") + "_" + safeName
		dst := filepath.Join(stageRoot, stageName)
		if err := c.SaveUploadedFile(fh, dst); err != nil {
			c.JSON(http.StatusInternalServerError, errJSON("Internal", "failed saving upload", gin.H{"err": err.Error()}))
			return
		}
		c.JSON(http.StatusCreated, gin.H{
			"staged_ref": dst,
			"size_bytes": fh.Size,
			"filename":   fh.Filename,
		})
		return
	}

	// Raw body upload fallback; filename from query.
	filename := sanitizeStageFilename(c.Query("filename"))
	if filename == "" {
		filename = "upload.wav"
	}
	stageName := time.Now().UTC().Format("20060102T150405.000000000Z") + "_" + filename
	dst := filepath.Join(stageRoot, stageName)
	f, ferr := os.Create(dst)
	if ferr != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "failed creating staged file", gin.H{"err": ferr.Error()}))
		return
	}
	defer f.Close()
	n, cerr := io.Copy(f, c.Request.Body)
	if cerr != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "failed writing staged file", gin.H{"err": cerr.Error()}))
		return
	}
	if n <= 0 {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "empty upload body", nil))
		return
	}
	c.JSON(http.StatusCreated, gin.H{
		"staged_ref": dst,
		"size_bytes": n,
		"filename":   filename,
	})
}

func sanitizeStageFilename(s string) string {
	x := strings.TrimSpace(s)
	if x == "" {
		return ""
	}
	x = filepath.Base(x)
	x = strings.ReplaceAll(x, "..", "")
	x = strings.ReplaceAll(x, "/", "_")
	x = strings.ReplaceAll(x, "\\", "_")
	x = strings.TrimSpace(x)
	if x == "" || x == "." || x == ".." {
		return ""
	}
	return x
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
