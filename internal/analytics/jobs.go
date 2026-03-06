package analytics

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

type JobType string

const (
	JobTypeFeatureEngineering JobType = "feature_engineering"
	JobTypePCA                JobType = "pca"
	JobTypeAudioAlignPLC      JobType = "audio_align_plc"
	JobTypeAudioInference     JobType = "audio_inference"
)

type JobStatus string

const (
	JobStatusQueued    JobStatus = "queued"
	JobStatusRunning   JobStatus = "running"
	JobStatusSucceeded JobStatus = "succeeded"
	JobStatusFailed    JobStatus = "failed"
)

type StorageTarget struct {
	Mode       string `json:"mode,omitempty"` // local_cache | s3 | both
	LocalCache bool   `json:"local_cache,omitempty"`
	S3         bool   `json:"s3,omitempty"`
}

type FeatureRunRequest struct {
	Site          string            `json:"site"`
	Day           string            `json:"day,omitempty"`
	DateFrom      string            `json:"date_from,omitempty"`
	DateTo        string            `json:"date_to,omitempty"`
	TimestampCol  string            `json:"timestamp_col,omitempty"`
	WindowSeconds int               `json:"window_seconds,omitempty"`
	StrideSeconds int               `json:"stride_seconds,omitempty"`
	MaxGapStaleS  float64           `json:"max_gap_stale_s,omitempty"`
	DataSource    string            `json:"data_source,omitempty"` // s3 | sql | local
	S3Bucket      string            `json:"s3_bucket,omitempty"`
	S3Prefix      string            `json:"s3_prefix,omitempty"`
	Options       map[string]any    `json:"options,omitempty"`
	Storage       *StorageTarget    `json:"storage,omitempty"`
	Tags          map[string]string `json:"tags,omitempty"`
}

type PCARunRequest struct {
	Site              string            `json:"site,omitempty"`
	InputArtifactID   string            `json:"input_artifact_id,omitempty"`
	InputURI          string            `json:"input_uri,omitempty"`
	Day               string            `json:"day,omitempty"`
	DateFrom          string            `json:"date_from,omitempty"`
	DateTo            string            `json:"date_to,omitempty"`
	WindowSeconds     int               `json:"window_seconds,omitempty"`
	StrideSeconds     int               `json:"stride_seconds,omitempty"`
	NComponents       int               `json:"n_components,omitempty"`
	Whiten            bool              `json:"whiten,omitempty"`
	Standardize       *bool             `json:"standardize,omitempty"`
	FillValue         *float64          `json:"fill_value,omitempty"`
	ClipAbs           *float64          `json:"clip_abs,omitempty"`
	ControlsWeight    *float64          `json:"controls_weight,omitempty"`
	IncludeRegex      []string          `json:"include_regex,omitempty"`
	ExcludeRegex      []string          `json:"exclude_regex,omitempty"`
	DropCols          []string          `json:"drop_cols,omitempty"`
	DropUnknown       bool              `json:"drop_unknown,omitempty"`
	DataSource        string            `json:"data_source,omitempty"` // s3 | local
	S3Bucket          string            `json:"s3_bucket,omitempty"`
	S3Prefix          string            `json:"s3_prefix,omitempty"`
	Storage           *StorageTarget    `json:"storage,omitempty"`
	ReturnProjection  bool              `json:"return_projection,omitempty"`
	MaxProjectionRows int               `json:"max_projection_rows,omitempty"`
	Tags              map[string]string `json:"tags,omitempty"`
}

type AudioAlignPLCRunRequest struct {
	Site              string            `json:"site"`
	Date              string            `json:"date"` // UTC day partition (audio_start day)
	AudioBucket       string            `json:"audio_bucket,omitempty"`
	AudioPrefix       string            `json:"audio_prefix,omitempty"` // partition prefix for the target day
	PLCBucket         string            `json:"plc_bucket,omitempty"`
	PLCPrefix         string            `json:"plc_prefix,omitempty"`
	TimestampCol      string            `json:"timestamp_col,omitempty"`
	AlignmentOffsetMS float64           `json:"alignment_offset_ms,omitempty"`
	PLCCols           []string          `json:"plc_cols,omitempty"`
	Storage           *StorageTarget    `json:"storage,omitempty"`
	OutS3Bucket       string            `json:"out_s3_bucket,omitempty"`
	OutS3Prefix       string            `json:"out_s3_prefix,omitempty"`
	Tags              map[string]string `json:"tags,omitempty"`
}

type Job struct {
	ID          string          `json:"id"`
	Type        JobType         `json:"type"`
	Status      JobStatus       `json:"status"`
	CreatedAt   time.Time       `json:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at"`
	StartedAt   *time.Time      `json:"started_at,omitempty"`
	FinishedAt  *time.Time      `json:"finished_at,omitempty"`
	Site        string          `json:"site,omitempty"`
	CreatedBy   string          `json:"created_by,omitempty"`
	RequestJSON json.RawMessage `json:"request_json,omitempty"`
	Result      map[string]any  `json:"result,omitempty"`
	Error       string          `json:"error,omitempty"`
}

type Store struct {
	mu      sync.RWMutex
	counter uint64
	jobs    map[string]Job
}

func NewStore() *Store {
	return &Store{jobs: make(map[string]Job)}
}

func (s *Store) CreateJob(ctx context.Context, jobType JobType, site, createdBy string, req any) (Job, error) {
	_ = ctx
	if s == nil {
		return Job{}, fmt.Errorf("analytics store not configured")
	}
	id := fmt.Sprintf("an-%d-%06d", time.Now().UTC().Unix(), atomic.AddUint64(&s.counter, 1))
	now := time.Now().UTC()
	raw, err := json.Marshal(req)
	if err != nil {
		return Job{}, fmt.Errorf("marshal request: %w", err)
	}
	job := Job{
		ID:          id,
		Type:        jobType,
		Status:      JobStatusQueued,
		CreatedAt:   now,
		UpdatedAt:   now,
		Site:        strings.ToLower(strings.TrimSpace(site)),
		CreatedBy:   strings.TrimSpace(createdBy),
		RequestJSON: raw,
		Result:      map[string]any{},
	}
	s.mu.Lock()
	s.jobs[id] = job
	s.mu.Unlock()
	return job, nil
}

func (s *Store) MarkRunning(ctx context.Context, id string) (Job, error) {
	_ = ctx
	if s == nil {
		return Job{}, fmt.Errorf("analytics store not configured")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	job, ok := s.jobs[id]
	if !ok {
		return Job{}, fmt.Errorf("job not found: %s", id)
	}
	now := time.Now().UTC()
	job.Status = JobStatusRunning
	job.UpdatedAt = now
	job.StartedAt = &now
	s.jobs[id] = job
	return job, nil
}

func (s *Store) MarkSucceeded(ctx context.Context, id string, result map[string]any) (Job, error) {
	_ = ctx
	if s == nil {
		return Job{}, fmt.Errorf("analytics store not configured")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	job, ok := s.jobs[id]
	if !ok {
		return Job{}, fmt.Errorf("job not found: %s", id)
	}
	now := time.Now().UTC()
	job.Status = JobStatusSucceeded
	job.UpdatedAt = now
	job.FinishedAt = &now
	job.Error = ""
	if result != nil {
		job.Result = result
	}
	s.jobs[id] = job
	return job, nil
}

func (s *Store) MarkFailed(ctx context.Context, id string, err error, partialResult map[string]any) (Job, error) {
	_ = ctx
	if s == nil {
		return Job{}, fmt.Errorf("analytics store not configured")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	job, ok := s.jobs[id]
	if !ok {
		return Job{}, fmt.Errorf("job not found: %s", id)
	}
	now := time.Now().UTC()
	job.Status = JobStatusFailed
	job.UpdatedAt = now
	job.FinishedAt = &now
	if err != nil {
		job.Error = err.Error()
	}
	if partialResult != nil {
		job.Result = partialResult
	}
	s.jobs[id] = job
	return job, nil
}

func (s *Store) GetJob(ctx context.Context, id string) (Job, bool) {
	_ = ctx
	if s == nil {
		return Job{}, false
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	job, ok := s.jobs[id]
	return job, ok
}

func (s *Store) ListJobs(ctx context.Context, limit int, offset int) []Job {
	_ = ctx
	if s == nil {
		return nil
	}
	if limit <= 0 || limit > 200 {
		limit = 50
	}
	if offset < 0 {
		offset = 0
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	all := make([]Job, 0, len(s.jobs))
	for _, j := range s.jobs {
		all = append(all, j)
	}
	return sliceJobsNewest(all, limit, offset)
}

func sliceJobsNewest(all []Job, limit, offset int) []Job {
	sort.Slice(all, func(i, j int) bool {
		if all[i].CreatedAt.Equal(all[j].CreatedAt) {
			return all[i].ID > all[j].ID
		}
		return all[i].CreatedAt.After(all[j].CreatedAt)
	})
	if offset >= len(all) {
		return []Job{}
	}
	end := offset + limit
	if end > len(all) {
		end = len(all)
	}
	out := make([]Job, end-offset)
	copy(out, all[offset:end])
	return out
}
