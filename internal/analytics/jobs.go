package analytics

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/jmoiron/sqlx"
)

const analyticsJobsTable = "analytics_jobs"

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

type jobRow struct {
	ID          string         `db:"id"`
	Type        string         `db:"type"`
	Status      string         `db:"status"`
	CreatedAt   time.Time      `db:"created_at"`
	UpdatedAt   time.Time      `db:"updated_at"`
	StartedAt   sql.NullTime   `db:"started_at"`
	FinishedAt  sql.NullTime   `db:"finished_at"`
	Site        sql.NullString `db:"site"`
	CreatedBy   sql.NullString `db:"created_by"`
	RequestJSON sql.NullString `db:"request_json"`
	ResultJSON  sql.NullString `db:"result_json"`
	Error       sql.NullString `db:"error"`
}

type Store struct {
	mu      sync.RWMutex
	counter uint64
	jobs    map[string]Job
	DB      *sqlx.DB
	Driver  string
}

func NewStore() *Store {
	return &Store{jobs: make(map[string]Job)}
}

func NewSQLStore(client *database.SQLXClient) *Store {
	if client == nil {
		return NewStore()
	}
	return &Store{
		jobs:   make(map[string]Job),
		DB:     client.DB,
		Driver: client.Driver,
	}
}

func (s *Store) EnsureSchema(ctx context.Context) error {
	if s == nil || s.DB == nil {
		return nil
	}
	timeType := "TIMESTAMP"
	jsonType := "TEXT"
	if s.Driver == "postgres" {
		timeType = "TIMESTAMPTZ"
		jsonType = "JSONB"
	}
	query := fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %s (
		id TEXT PRIMARY KEY,
		type TEXT NOT NULL,
		status TEXT NOT NULL,
		created_at %s NOT NULL,
		updated_at %s NOT NULL,
		started_at %s,
		finished_at %s,
		site TEXT,
		created_by TEXT,
		request_json %s,
		result_json %s,
		error TEXT
	)`, analyticsJobsTable, timeType, timeType, timeType, timeType, jsonType, jsonType)
	if _, err := s.DB.ExecContext(ctx, query); err != nil {
		return fmt.Errorf("create analytics_jobs: %w", err)
	}
	for _, idx := range []string{
		"CREATE INDEX IF NOT EXISTS analytics_jobs_status_updated_idx ON analytics_jobs(status, updated_at DESC)",
		"CREATE INDEX IF NOT EXISTS analytics_jobs_site_created_idx ON analytics_jobs(site, created_at DESC)",
	} {
		if _, err := s.DB.ExecContext(ctx, idx); err != nil {
			return fmt.Errorf("create analytics_jobs index: %w", err)
		}
	}
	return nil
}

func (s *Store) CreateJob(ctx context.Context, jobType JobType, site, createdBy string, req any) (Job, error) {
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
	if s.DB != nil {
		resultRaw, _ := json.Marshal(job.Result)
		_, err := s.namedExec(ctx, `INSERT INTO analytics_jobs
			(id, type, status, created_at, updated_at, started_at, finished_at, site, created_by, request_json, result_json, error)
			VALUES (:id, :type, :status, :created_at, :updated_at, :started_at, :finished_at, :site, :created_by, :request_json, :result_json, :error)`, map[string]any{
			"id":           job.ID,
			"type":         job.Type,
			"status":       job.Status,
			"created_at":   job.CreatedAt,
			"updated_at":   job.UpdatedAt,
			"started_at":   job.StartedAt,
			"finished_at":  job.FinishedAt,
			"site":         nullIfBlank(job.Site),
			"created_by":   nullIfBlank(job.CreatedBy),
			"request_json": string(raw),
			"result_json":  string(resultRaw),
			"error":        nullIfBlank(job.Error),
		})
		if err != nil {
			return Job{}, fmt.Errorf("create analytics job: %w", err)
		}
		return job, nil
	}
	s.mu.Lock()
	s.jobs[id] = job
	s.mu.Unlock()
	return job, nil
}

func (s *Store) MarkRunning(ctx context.Context, id string) (Job, error) {
	if s == nil {
		return Job{}, fmt.Errorf("analytics store not configured")
	}
	if s.DB != nil {
		now := time.Now().UTC()
		if _, err := s.namedExec(ctx, `UPDATE analytics_jobs SET status = :status, updated_at = :updated_at, started_at = :started_at WHERE id = :id`, map[string]any{
			"id":         id,
			"status":     JobStatusRunning,
			"updated_at": now,
			"started_at": now,
		}); err != nil {
			return Job{}, fmt.Errorf("mark analytics job running: %w", err)
		}
		return s.getJobSQL(ctx, id)
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
	if s == nil {
		return Job{}, fmt.Errorf("analytics store not configured")
	}
	if s.DB != nil {
		now := time.Now().UTC()
		resultRaw, err := json.Marshal(result)
		if err != nil {
			return Job{}, fmt.Errorf("marshal analytics job result: %w", err)
		}
		if _, err := s.namedExec(ctx, `UPDATE analytics_jobs SET status = :status, updated_at = :updated_at, finished_at = :finished_at, result_json = :result_json, error = '' WHERE id = :id`, map[string]any{
			"id":          id,
			"status":      JobStatusSucceeded,
			"updated_at":  now,
			"finished_at": now,
			"result_json": string(resultRaw),
		}); err != nil {
			return Job{}, fmt.Errorf("mark analytics job succeeded: %w", err)
		}
		return s.getJobSQL(ctx, id)
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
	if s == nil {
		return Job{}, fmt.Errorf("analytics store not configured")
	}
	if s.DB != nil {
		now := time.Now().UTC()
		msg := ""
		if err != nil {
			msg = err.Error()
		}
		resultRaw, marshalErr := json.Marshal(partialResult)
		if marshalErr != nil {
			return Job{}, fmt.Errorf("marshal analytics job partial result: %w", marshalErr)
		}
		if _, updateErr := s.namedExec(ctx, `UPDATE analytics_jobs SET status = :status, updated_at = :updated_at, finished_at = :finished_at, result_json = :result_json, error = :error WHERE id = :id`, map[string]any{
			"id":          id,
			"status":      JobStatusFailed,
			"updated_at":  now,
			"finished_at": now,
			"result_json": string(resultRaw),
			"error":       msg,
		}); updateErr != nil {
			return Job{}, fmt.Errorf("mark analytics job failed: %w", updateErr)
		}
		return s.getJobSQL(ctx, id)
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
	if s == nil {
		return Job{}, false
	}
	if s.DB != nil {
		job, err := s.getJobSQL(ctx, id)
		return job, err == nil
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	job, ok := s.jobs[id]
	return job, ok
}

func (s *Store) ListJobs(ctx context.Context, limit int, offset int) []Job {
	if s == nil {
		return nil
	}
	if limit <= 0 || limit > 200 {
		limit = 50
	}
	if offset < 0 {
		offset = 0
	}
	if s.DB != nil {
		jobs, err := s.listJobsSQL(ctx, limit, offset)
		if err != nil {
			return nil
		}
		return jobs
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	all := make([]Job, 0, len(s.jobs))
	for _, j := range s.jobs {
		all = append(all, j)
	}
	return sliceJobsNewest(all, limit, offset)
}

func (s *Store) getJobSQL(ctx context.Context, id string) (Job, error) {
	var row jobRow
	query := `SELECT id, type, status, created_at, updated_at, started_at, finished_at, site, created_by, request_json, result_json, error
		FROM analytics_jobs WHERE id = ?`
	if err := s.DB.GetContext(ctx, &row, s.DB.Rebind(query), strings.TrimSpace(id)); err != nil {
		return Job{}, err
	}
	return row.toJob()
}

func (s *Store) listJobsSQL(ctx context.Context, limit, offset int) ([]Job, error) {
	var rows []jobRow
	query := `SELECT id, type, status, created_at, updated_at, started_at, finished_at, site, created_by, request_json, result_json, error
		FROM analytics_jobs ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?`
	if err := s.DB.SelectContext(ctx, &rows, s.DB.Rebind(query), limit, offset); err != nil {
		return nil, err
	}
	out := make([]Job, 0, len(rows))
	for _, row := range rows {
		job, err := row.toJob()
		if err != nil {
			return nil, err
		}
		out = append(out, job)
	}
	return out, nil
}

func (s *Store) namedExec(ctx context.Context, query string, args map[string]any) (sql.Result, error) {
	q, params, err := sqlx.Named(query, args)
	if err != nil {
		return nil, err
	}
	return s.DB.ExecContext(ctx, s.DB.Rebind(q), params...)
}

func (r jobRow) toJob() (Job, error) {
	job := Job{
		ID:        r.ID,
		Type:      JobType(r.Type),
		Status:    JobStatus(r.Status),
		CreatedAt: r.CreatedAt,
		UpdatedAt: r.UpdatedAt,
		Result:    map[string]any{},
	}
	if r.StartedAt.Valid {
		job.StartedAt = &r.StartedAt.Time
	}
	if r.FinishedAt.Valid {
		job.FinishedAt = &r.FinishedAt.Time
	}
	if r.Site.Valid {
		job.Site = r.Site.String
	}
	if r.CreatedBy.Valid {
		job.CreatedBy = r.CreatedBy.String
	}
	if r.RequestJSON.Valid && strings.TrimSpace(r.RequestJSON.String) != "" {
		job.RequestJSON = json.RawMessage(r.RequestJSON.String)
	}
	if r.ResultJSON.Valid && strings.TrimSpace(r.ResultJSON.String) != "" {
		if err := json.Unmarshal([]byte(r.ResultJSON.String), &job.Result); err != nil {
			return Job{}, fmt.Errorf("decode analytics job result: %w", err)
		}
	}
	if r.Error.Valid {
		job.Error = r.Error.String
	}
	return job, nil
}

func nullIfBlank(s string) any {
	if strings.TrimSpace(s) == "" {
		return nil
	}
	return s
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
