package audio

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/jmoiron/sqlx"
)

type Store struct {
	DB     *sqlx.DB
	Driver string
}

type AudioSource struct {
	ID          int64     `json:"id"`
	Site        string    `json:"site"`
	SourceKey   string    `json:"source_key"`
	DisplayName string    `json:"display_name"`
	Description string    `json:"description,omitempty"`
	IsActive    bool      `json:"is_active"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

type UpsertAudioSource struct {
	Site        string
	SourceKey   string
	DisplayName string
	Description string
	IsActive    *bool
}

type ListAudioSources struct {
	Site string
}

type AudioArtifact struct {
	ID          int64           `json:"id"`
	Site        string          `json:"site"`
	SourceID    int64           `json:"source_id"`
	SourceKey   string          `json:"source_key"`
	DisplayName string          `json:"display_name,omitempty"`
	S3Bucket    string          `json:"s3_bucket"`
	S3Key       string          `json:"s3_key"`
	PublicURL   string          `json:"public_url,omitempty"`
	UTCDay      string          `json:"utc_day"`
	StartTime   time.Time       `json:"start_time"`
	EndTime     time.Time       `json:"end_time"`
	DurationMS  int             `json:"duration_ms"`
	Format      string          `json:"format"`
	ContentType string          `json:"content_type,omitempty"`
	SizeBytes   *int64          `json:"size_bytes,omitempty"`
	ETag        string          `json:"etag,omitempty"`
	Metadata    json.RawMessage `json:"metadata,omitempty"`
	CreatedAt   time.Time       `json:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at"`
}

type UpsertAudioArtifact struct {
	Site        string
	SourceID    int64
	S3Bucket    string
	S3Key       string
	PublicURL   string
	UTCDay      *time.Time
	StartTime   time.Time
	EndTime     time.Time
	DurationMS  int
	Format      string
	ContentType string
	SizeBytes   *int64
	ETag        string
	Metadata    json.RawMessage
}

type ListAudioArtifacts struct {
	Site      string
	SourceKey string
	Format    string
	Start     *time.Time
	End       *time.Time
	Limit     int
	Offset    int
}

type sourceRow struct {
	ID          int64          `db:"id"`
	Site        string         `db:"site"`
	SourceKey   string         `db:"source_key"`
	DisplayName string         `db:"display_name"`
	Description sql.NullString `db:"description"`
	IsActive    bool           `db:"is_active"`
	CreatedAt   time.Time      `db:"created_at"`
	UpdatedAt   time.Time      `db:"updated_at"`
}

type artifactRow struct {
	ID          int64          `db:"id"`
	Site        string         `db:"site"`
	SourceID    int64          `db:"source_id"`
	SourceKey   string         `db:"source_key"`
	DisplayName sql.NullString `db:"display_name"`
	S3Bucket    string         `db:"s3_bucket"`
	S3Key       string         `db:"s3_key"`
	PublicURL   sql.NullString `db:"public_url"`
	UTCDay      string         `db:"utc_day"`
	StartTime   time.Time      `db:"start_time"`
	EndTime     time.Time      `db:"end_time"`
	DurationMS  int            `db:"duration_ms"`
	Format      string         `db:"format"`
	ContentType sql.NullString `db:"content_type"`
	SizeBytes   sql.NullInt64  `db:"size_bytes"`
	ETag        sql.NullString `db:"etag"`
	Metadata    sql.NullString `db:"metadata_json"`
	CreatedAt   time.Time      `db:"created_at"`
	UpdatedAt   time.Time      `db:"updated_at"`
}

func NewStore(client *database.SQLXClient) *Store {
	if client == nil {
		return nil
	}
	return &Store{DB: client.DB, Driver: client.Driver}
}

func (s *Store) EnsureSchema(ctx context.Context) error {
	if s == nil {
		return nil
	}

	sourcesDDL := `CREATE TABLE IF NOT EXISTS audio_sources (
		id BIGSERIAL PRIMARY KEY,
		site TEXT NOT NULL,
		source_key TEXT NOT NULL,
		display_name TEXT NOT NULL,
		description TEXT,
		is_active BOOLEAN NOT NULL DEFAULT TRUE,
		created_at TIMESTAMPTZ NOT NULL,
		updated_at TIMESTAMPTZ NOT NULL,
		UNIQUE (site, source_key)
	)`
	artifactsDDL := `CREATE TABLE IF NOT EXISTS audio_artifacts (
		id BIGSERIAL PRIMARY KEY,
		site TEXT NOT NULL,
		source_id BIGINT NOT NULL REFERENCES audio_sources(id) ON DELETE RESTRICT,
		s3_bucket TEXT NOT NULL,
		s3_key TEXT NOT NULL,
		public_url TEXT,
		utc_day DATE NOT NULL,
		start_time TIMESTAMPTZ NOT NULL,
		end_time TIMESTAMPTZ NOT NULL,
		duration_ms INTEGER NOT NULL,
		format TEXT NOT NULL,
		content_type TEXT,
		size_bytes BIGINT,
		etag TEXT,
		metadata_json TEXT,
		created_at TIMESTAMPTZ NOT NULL,
		updated_at TIMESTAMPTZ NOT NULL,
		UNIQUE (s3_bucket, s3_key)
	)`

	if s.Driver != "postgres" {
		sourcesDDL = `CREATE TABLE IF NOT EXISTS audio_sources (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			site TEXT NOT NULL,
			source_key TEXT NOT NULL,
			display_name TEXT NOT NULL,
			description TEXT,
			is_active BOOLEAN NOT NULL DEFAULT 1,
			created_at TIMESTAMP NOT NULL,
			updated_at TIMESTAMP NOT NULL,
			UNIQUE (site, source_key)
		)`
		artifactsDDL = `CREATE TABLE IF NOT EXISTS audio_artifacts (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			site TEXT NOT NULL,
			source_id INTEGER NOT NULL REFERENCES audio_sources(id) ON DELETE RESTRICT,
			s3_bucket TEXT NOT NULL,
			s3_key TEXT NOT NULL,
			public_url TEXT,
			utc_day DATE NOT NULL,
			start_time TIMESTAMP NOT NULL,
			end_time TIMESTAMP NOT NULL,
			duration_ms INTEGER NOT NULL,
			format TEXT NOT NULL,
			content_type TEXT,
			size_bytes INTEGER,
			etag TEXT,
			metadata_json TEXT,
			created_at TIMESTAMP NOT NULL,
			updated_at TIMESTAMP NOT NULL,
			UNIQUE (s3_bucket, s3_key)
		)`
	}

	if _, err := s.DB.ExecContext(ctx, sourcesDDL); err != nil {
		return fmt.Errorf("create audio_sources: %w", err)
	}
	if _, err := s.DB.ExecContext(ctx, artifactsDDL); err != nil {
		return fmt.Errorf("create audio_artifacts: %w", err)
	}

	indexes := []string{
		"CREATE INDEX IF NOT EXISTS audio_sources_site_source_key_idx ON audio_sources(site, source_key)",
		"CREATE INDEX IF NOT EXISTS audio_artifacts_site_start_time_idx ON audio_artifacts(site, start_time DESC)",
		"CREATE INDEX IF NOT EXISTS audio_artifacts_source_time_idx ON audio_artifacts(source_id, start_time DESC)",
		"CREATE INDEX IF NOT EXISTS audio_artifacts_utc_day_site_idx ON audio_artifacts(utc_day, site)",
		"CREATE INDEX IF NOT EXISTS audio_artifacts_site_range_idx ON audio_artifacts(site, start_time, end_time)",
	}
	for _, idx := range indexes {
		if _, err := s.DB.ExecContext(ctx, idx); err != nil {
			return fmt.Errorf("create index: %w", err)
		}
	}
	return nil
}

func (s *Store) UpsertAudioSource(ctx context.Context, input UpsertAudioSource) (AudioSource, error) {
	if s == nil {
		return AudioSource{}, fmt.Errorf("store not configured")
	}
	now := time.Now().UTC()
	site := strings.ToLower(strings.TrimSpace(input.Site))
	sourceKey := strings.ToLower(strings.TrimSpace(input.SourceKey))
	displayName := strings.TrimSpace(input.DisplayName)
	if displayName == "" {
		displayName = sourceKey
	}
	isActive := true
	if input.IsActive != nil {
		isActive = *input.IsActive
	}

	args := map[string]any{
		"site":         site,
		"source_key":   sourceKey,
		"display_name": displayName,
		"description":  nullIfEmpty(strings.TrimSpace(input.Description)),
		"is_active":    isActive,
		"created_at":   now,
		"updated_at":   now,
	}

	query := `INSERT INTO audio_sources(site, source_key, display_name, description, is_active, created_at, updated_at)
		VALUES (:site, :source_key, :display_name, :description, :is_active, :created_at, :updated_at)
		ON CONFLICT (site, source_key) DO UPDATE SET
			display_name = EXCLUDED.display_name,
			description = EXCLUDED.description,
			is_active = EXCLUDED.is_active,
			updated_at = EXCLUDED.updated_at`
	if s.Driver == "postgres" {
		query += ` RETURNING id`
	}
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return AudioSource{}, fmt.Errorf("upsert audio_source: %w", err)
	}
	query = s.DB.Rebind(query)

	if s.Driver == "postgres" {
		var id int64
		if err := s.DB.GetContext(ctx, &id, query, params...); err != nil {
			return AudioSource{}, fmt.Errorf("upsert audio_source: %w", err)
		}
		return s.GetAudioSource(ctx, id)
	}
	if _, err := s.DB.ExecContext(ctx, query, params...); err != nil {
		return AudioSource{}, fmt.Errorf("upsert audio_source: %w", err)
	}
	return s.GetAudioSourceBySiteKey(ctx, site, sourceKey)
}

func (s *Store) GetAudioSource(ctx context.Context, id int64) (AudioSource, error) {
	if s == nil {
		return AudioSource{}, fmt.Errorf("store not configured")
	}
	query := `SELECT id, site, source_key, display_name, description, is_active, created_at, updated_at
		FROM audio_sources WHERE id = :id`
	query, params, err := sqlx.Named(query, map[string]any{"id": id})
	if err != nil {
		return AudioSource{}, fmt.Errorf("get audio_source: %w", err)
	}
	query = s.DB.Rebind(query)
	var row sourceRow
	if err := s.DB.GetContext(ctx, &row, query, params...); err != nil {
		return AudioSource{}, err
	}
	return row.toAudioSource(), nil
}

func (s *Store) GetAudioSourceBySiteKey(ctx context.Context, site, sourceKey string) (AudioSource, error) {
	if s == nil {
		return AudioSource{}, fmt.Errorf("store not configured")
	}
	query := `SELECT id, site, source_key, display_name, description, is_active, created_at, updated_at
		FROM audio_sources WHERE site = :site AND source_key = :source_key`
	query, params, err := sqlx.Named(query, map[string]any{
		"site":       strings.ToLower(strings.TrimSpace(site)),
		"source_key": strings.ToLower(strings.TrimSpace(sourceKey)),
	})
	if err != nil {
		return AudioSource{}, fmt.Errorf("get audio_source by site/key: %w", err)
	}
	query = s.DB.Rebind(query)
	var row sourceRow
	if err := s.DB.GetContext(ctx, &row, query, params...); err != nil {
		return AudioSource{}, err
	}
	return row.toAudioSource(), nil
}

func (s *Store) ListAudioSources(ctx context.Context, opts ListAudioSources) ([]AudioSource, error) {
	if s == nil {
		return nil, fmt.Errorf("store not configured")
	}
	args := map[string]any{}
	query := `SELECT id, site, source_key, display_name, description, is_active, created_at, updated_at
		FROM audio_sources WHERE 1=1`
	if site := strings.ToLower(strings.TrimSpace(opts.Site)); site != "" {
		query += " AND site = :site"
		args["site"] = site
	}
	query += " ORDER BY site ASC, source_key ASC"
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return nil, fmt.Errorf("list audio_sources: %w", err)
	}
	query = s.DB.Rebind(query)
	var rows []sourceRow
	if err := s.DB.SelectContext(ctx, &rows, query, params...); err != nil {
		return nil, err
	}
	out := make([]AudioSource, 0, len(rows))
	for _, row := range rows {
		out = append(out, row.toAudioSource())
	}
	return out, nil
}

func (s *Store) UpsertAudioArtifact(ctx context.Context, input UpsertAudioArtifact) (AudioArtifact, error) {
	if s == nil {
		return AudioArtifact{}, fmt.Errorf("store not configured")
	}
	now := time.Now().UTC()
	site := strings.ToLower(strings.TrimSpace(input.Site))
	format := strings.ToLower(strings.TrimSpace(input.Format))
	utcDay := now.Format("2006-01-02")
	if input.UTCDay != nil {
		utcDay = input.UTCDay.UTC().Format("2006-01-02")
	} else if !input.StartTime.IsZero() {
		utcDay = input.StartTime.UTC().Format("2006-01-02")
	}
	durationMS := input.DurationMS
	if durationMS <= 0 && !input.StartTime.IsZero() && !input.EndTime.IsZero() && input.EndTime.After(input.StartTime) {
		durationMS = int(input.EndTime.Sub(input.StartTime) / time.Millisecond)
	}

	args := map[string]any{
		"site":         site,
		"source_id":    input.SourceID,
		"s3_bucket":    strings.TrimSpace(input.S3Bucket),
		"s3_key":       strings.TrimSpace(input.S3Key),
		"public_url":   nullIfEmpty(strings.TrimSpace(input.PublicURL)),
		"utc_day":      utcDay,
		"start_time":   input.StartTime.UTC(),
		"end_time":     input.EndTime.UTC(),
		"duration_ms":  durationMS,
		"format":       format,
		"content_type": nullIfEmpty(strings.TrimSpace(input.ContentType)),
		"size_bytes":   input.SizeBytes,
		"etag":         nullIfEmpty(strings.TrimSpace(input.ETag)),
		"metadata_json": func() any {
			if len(input.Metadata) == 0 {
				return nil
			}
			return string(input.Metadata)
		}(),
		"created_at": now,
		"updated_at": now,
	}

	query := `INSERT INTO audio_artifacts(site, source_id, s3_bucket, s3_key, public_url, utc_day, start_time, end_time, duration_ms, format, content_type, size_bytes, etag, metadata_json, created_at, updated_at)
		VALUES (:site, :source_id, :s3_bucket, :s3_key, :public_url, :utc_day, :start_time, :end_time, :duration_ms, :format, :content_type, :size_bytes, :etag, :metadata_json, :created_at, :updated_at)
		ON CONFLICT (s3_bucket, s3_key) DO UPDATE SET
			site = EXCLUDED.site,
			source_id = EXCLUDED.source_id,
			public_url = EXCLUDED.public_url,
			utc_day = EXCLUDED.utc_day,
			start_time = EXCLUDED.start_time,
			end_time = EXCLUDED.end_time,
			duration_ms = EXCLUDED.duration_ms,
			format = EXCLUDED.format,
			content_type = EXCLUDED.content_type,
			size_bytes = EXCLUDED.size_bytes,
			etag = EXCLUDED.etag,
			metadata_json = EXCLUDED.metadata_json,
			updated_at = EXCLUDED.updated_at`
	if s.Driver == "postgres" {
		query += ` RETURNING id`
	}
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return AudioArtifact{}, fmt.Errorf("upsert audio_artifact: %w", err)
	}
	query = s.DB.Rebind(query)

	if s.Driver == "postgres" {
		var id int64
		if err := s.DB.GetContext(ctx, &id, query, params...); err != nil {
			return AudioArtifact{}, fmt.Errorf("upsert audio_artifact: %w", err)
		}
		return s.GetAudioArtifact(ctx, id)
	}
	if _, err := s.DB.ExecContext(ctx, query, params...); err != nil {
		return AudioArtifact{}, fmt.Errorf("upsert audio_artifact: %w", err)
	}
	return s.GetAudioArtifactByS3Key(ctx, strings.TrimSpace(input.S3Bucket), strings.TrimSpace(input.S3Key))
}

func (s *Store) GetAudioArtifact(ctx context.Context, id int64) (AudioArtifact, error) {
	if s == nil {
		return AudioArtifact{}, fmt.Errorf("store not configured")
	}
	query := artifactSelectBase() + ` WHERE a.id = :id`
	query, params, err := sqlx.Named(query, map[string]any{"id": id})
	if err != nil {
		return AudioArtifact{}, fmt.Errorf("get audio_artifact: %w", err)
	}
	query = s.DB.Rebind(query)
	var row artifactRow
	if err := s.DB.GetContext(ctx, &row, query, params...); err != nil {
		return AudioArtifact{}, err
	}
	return row.toAudioArtifact(), nil
}

func (s *Store) GetAudioArtifactByS3Key(ctx context.Context, bucket, key string) (AudioArtifact, error) {
	if s == nil {
		return AudioArtifact{}, fmt.Errorf("store not configured")
	}
	query := artifactSelectBase() + ` WHERE a.s3_bucket = :s3_bucket AND a.s3_key = :s3_key`
	query, params, err := sqlx.Named(query, map[string]any{
		"s3_bucket": strings.TrimSpace(bucket),
		"s3_key":    strings.TrimSpace(key),
	})
	if err != nil {
		return AudioArtifact{}, fmt.Errorf("get audio_artifact by s3 key: %w", err)
	}
	query = s.DB.Rebind(query)
	var row artifactRow
	if err := s.DB.GetContext(ctx, &row, query, params...); err != nil {
		return AudioArtifact{}, err
	}
	return row.toAudioArtifact(), nil
}

func (s *Store) ListAudioArtifacts(ctx context.Context, opts ListAudioArtifacts) ([]AudioArtifact, error) {
	if s == nil {
		return nil, fmt.Errorf("store not configured")
	}
	limit := opts.Limit
	if limit <= 0 || limit > 200 {
		limit = 50
	}
	offset := opts.Offset
	if offset < 0 {
		offset = 0
	}

	args := map[string]any{
		"limit":  limit,
		"offset": offset,
	}
	query := artifactSelectBase() + " WHERE 1=1"
	if site := strings.ToLower(strings.TrimSpace(opts.Site)); site != "" {
		query += " AND a.site = :site"
		args["site"] = site
	}
	if sourceKey := strings.ToLower(strings.TrimSpace(opts.SourceKey)); sourceKey != "" {
		query += " AND s.source_key = :source_key"
		args["source_key"] = sourceKey
	}
	if format := strings.ToLower(strings.TrimSpace(opts.Format)); format != "" {
		query += " AND a.format = :format"
		args["format"] = format
	}
	if opts.Start != nil {
		query += " AND a.end_time >= :start"
		args["start"] = opts.Start.UTC()
	}
	if opts.End != nil {
		query += " AND a.start_time <= :end"
		args["end"] = opts.End.UTC()
	}
	query += " ORDER BY a.start_time DESC LIMIT :limit OFFSET :offset"

	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return nil, fmt.Errorf("list audio_artifacts: %w", err)
	}
	query = s.DB.Rebind(query)
	var rows []artifactRow
	if err := s.DB.SelectContext(ctx, &rows, query, params...); err != nil {
		return nil, err
	}
	out := make([]AudioArtifact, 0, len(rows))
	for _, row := range rows {
		out = append(out, row.toAudioArtifact())
	}
	return out, nil
}

func (s *Store) CountAudioArtifacts(ctx context.Context, opts ListAudioArtifacts) (int, error) {
	if s == nil {
		return 0, fmt.Errorf("store not configured")
	}
	args := map[string]any{}
	query := `SELECT COUNT(*)
		FROM audio_artifacts a
		JOIN audio_sources s ON s.id = a.source_id
		WHERE 1=1`
	if site := strings.ToLower(strings.TrimSpace(opts.Site)); site != "" {
		query += " AND a.site = :site"
		args["site"] = site
	}
	if sourceKey := strings.ToLower(strings.TrimSpace(opts.SourceKey)); sourceKey != "" {
		query += " AND s.source_key = :source_key"
		args["source_key"] = sourceKey
	}
	if format := strings.ToLower(strings.TrimSpace(opts.Format)); format != "" {
		query += " AND a.format = :format"
		args["format"] = format
	}
	if opts.Start != nil {
		query += " AND a.end_time >= :start"
		args["start"] = opts.Start.UTC()
	}
	if opts.End != nil {
		query += " AND a.start_time <= :end"
		args["end"] = opts.End.UTC()
	}
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return 0, fmt.Errorf("count audio_artifacts: %w", err)
	}
	query = s.DB.Rebind(query)
	var total int
	if err := s.DB.GetContext(ctx, &total, query, params...); err != nil {
		return 0, fmt.Errorf("count audio_artifacts: %w", err)
	}
	return total, nil
}

func artifactSelectBase() string {
	return `SELECT
		a.id,
		a.site,
		a.source_id,
		s.source_key,
		s.display_name,
		a.s3_bucket,
		a.s3_key,
		a.public_url,
		CAST(a.utc_day AS TEXT) AS utc_day,
		a.start_time,
		a.end_time,
		a.duration_ms,
		a.format,
		a.content_type,
		a.size_bytes,
		a.etag,
		a.metadata_json,
		a.created_at,
		a.updated_at
	FROM audio_artifacts a
	JOIN audio_sources s ON s.id = a.source_id`
}

func (r sourceRow) toAudioSource() AudioSource {
	return AudioSource{
		ID:          r.ID,
		Site:        r.Site,
		SourceKey:   r.SourceKey,
		DisplayName: r.DisplayName,
		Description: strings.TrimSpace(r.Description.String),
		IsActive:    r.IsActive,
		CreatedAt:   r.CreatedAt,
		UpdatedAt:   r.UpdatedAt,
	}
}

func (r artifactRow) toAudioArtifact() AudioArtifact {
	var sizeBytes *int64
	if r.SizeBytes.Valid {
		sizeBytes = &r.SizeBytes.Int64
	}
	var meta json.RawMessage
	if r.Metadata.Valid && strings.TrimSpace(r.Metadata.String) != "" {
		meta = json.RawMessage(r.Metadata.String)
	}
	return AudioArtifact{
		ID:          r.ID,
		Site:        r.Site,
		SourceID:    r.SourceID,
		SourceKey:   r.SourceKey,
		DisplayName: strings.TrimSpace(r.DisplayName.String),
		S3Bucket:    r.S3Bucket,
		S3Key:       r.S3Key,
		PublicURL:   strings.TrimSpace(r.PublicURL.String),
		UTCDay:      r.UTCDay,
		StartTime:   r.StartTime,
		EndTime:     r.EndTime,
		DurationMS:  r.DurationMS,
		Format:      r.Format,
		ContentType: strings.TrimSpace(r.ContentType.String),
		SizeBytes:   sizeBytes,
		ETag:        strings.TrimSpace(r.ETag.String),
		Metadata:    meta,
		CreatedAt:   r.CreatedAt,
		UpdatedAt:   r.UpdatedAt,
	}
}

func nullIfEmpty(v string) any {
	if strings.TrimSpace(v) == "" {
		return nil
	}
	return strings.TrimSpace(v)
}
