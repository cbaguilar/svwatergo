package grabsamples

import (
	"context"
	"database/sql"
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

type GrabSample struct {
	ID              int64      `json:"id"`
	Site            string     `json:"site"`
	SampleID        string     `json:"sample_id"`
	ExtractedAt     *time.Time `json:"extracted_at,omitempty"`
	ArrivedAt       *time.Time `json:"arrived_at,omitempty"`
	SampleTakenBy   string     `json:"sample_taken_by,omitempty"`
	RawFileName     string     `json:"raw_file_name,omitempty"`
	StorageProvider string     `json:"storage_provider,omitempty"`
	StorageBucket   string     `json:"storage_bucket,omitempty"`
	StorageKey      string     `json:"storage_key,omitempty"`
	FileURL         string     `json:"file_url,omitempty"`
	ParseStatus     string     `json:"parse_status,omitempty"`
	Notes           string     `json:"notes,omitempty"`
	CreatedAt       time.Time  `json:"created_at"`
	UpdatedAt       time.Time  `json:"updated_at"`
}

type CreateGrabSample struct {
	Site            string
	SampleID        string
	ExtractedAt     *time.Time
	ArrivedAt       *time.Time
	SampleTakenBy   string
	RawFileName     string
	StorageProvider string
	StorageBucket   string
	StorageKey      string
	FileURL         string
	ParseStatus     string
	Notes           string
}

type UpdateGrabSample struct {
	ExtractedAt     **time.Time
	ArrivedAt       **time.Time
	SampleTakenBy   *string
	RawFileName     *string
	StorageProvider *string
	StorageBucket   *string
	StorageKey      *string
	FileURL         *string
	ParseStatus     *string
	Notes           *string
}

type ListGrabSamples struct {
	Site   string
	Query  string
	Limit  int
	Offset int
}

type grabSampleRow struct {
	ID              int64          `db:"id"`
	Site            string         `db:"site"`
	SampleID        string         `db:"sample_id"`
	ExtractedAt     sql.NullTime   `db:"extracted_at"`
	ArrivedAt       sql.NullTime   `db:"arrived_at"`
	SampleTakenBy   sql.NullString `db:"sample_taken_by"`
	RawFileName     sql.NullString `db:"raw_file_name"`
	StorageProvider sql.NullString `db:"storage_provider"`
	StorageBucket   sql.NullString `db:"storage_bucket"`
	StorageKey      sql.NullString `db:"storage_key"`
	FileURL         sql.NullString `db:"file_url"`
	ParseStatus     sql.NullString `db:"parse_status"`
	Notes           sql.NullString `db:"notes"`
	CreatedAt       time.Time      `db:"created_at"`
	UpdatedAt       time.Time      `db:"updated_at"`
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
	var create string
	switch s.Driver {
	case "postgres":
		create = `CREATE TABLE IF NOT EXISTS grab_samples (
			id BIGSERIAL PRIMARY KEY,
			site TEXT NOT NULL,
			sample_id TEXT NOT NULL,
			extracted_at TIMESTAMPTZ,
			arrived_at TIMESTAMPTZ,
			sample_taken_by TEXT,
			raw_file_name TEXT,
			storage_provider TEXT,
			storage_bucket TEXT,
			storage_key TEXT,
			file_url TEXT,
			parse_status TEXT,
			notes TEXT,
			created_at TIMESTAMPTZ NOT NULL,
			updated_at TIMESTAMPTZ NOT NULL,
			UNIQUE (site, sample_id)
		)`
	default:
		create = `CREATE TABLE IF NOT EXISTS grab_samples (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			site TEXT NOT NULL,
			sample_id TEXT NOT NULL,
			extracted_at TIMESTAMP,
			arrived_at TIMESTAMP,
			sample_taken_by TEXT,
			raw_file_name TEXT,
			storage_provider TEXT,
			storage_bucket TEXT,
			storage_key TEXT,
			file_url TEXT,
			parse_status TEXT,
			notes TEXT,
			created_at TIMESTAMP NOT NULL,
			updated_at TIMESTAMP NOT NULL,
			UNIQUE (site, sample_id)
		)`
	}
	if _, err := s.DB.ExecContext(ctx, create); err != nil {
		return fmt.Errorf("create grab_samples: %w", err)
	}
	indexes := []string{
		"CREATE INDEX IF NOT EXISTS grab_samples_site_created_at_idx ON grab_samples(site, created_at DESC)",
		"CREATE INDEX IF NOT EXISTS grab_samples_site_extracted_at_idx ON grab_samples(site, extracted_at DESC)",
	}
	for _, idx := range indexes {
		if _, err := s.DB.ExecContext(ctx, idx); err != nil {
			return fmt.Errorf("create grab_samples index: %w", err)
		}
	}
	return nil
}

func (s *Store) CreateGrabSample(ctx context.Context, input CreateGrabSample) (GrabSample, error) {
	if s == nil {
		return GrabSample{}, fmt.Errorf("store not configured")
	}
	now := time.Now().UTC()
	sampleID := strings.TrimSpace(input.SampleID)
	if sampleID == "" {
		sampleID = now.Format("060102_150405.000")
	}
	args := map[string]any{
		"site":             strings.ToLower(strings.TrimSpace(input.Site)),
		"sample_id":        sampleID,
		"extracted_at":     input.ExtractedAt,
		"arrived_at":       input.ArrivedAt,
		"sample_taken_by":  nullIfEmpty(input.SampleTakenBy),
		"raw_file_name":    nullIfEmpty(input.RawFileName),
		"storage_provider": nullIfEmpty(input.StorageProvider),
		"storage_bucket":   nullIfEmpty(input.StorageBucket),
		"storage_key":      nullIfEmpty(input.StorageKey),
		"file_url":         nullIfEmpty(input.FileURL),
		"parse_status":     nullIfEmpty(defaultParseStatus(input.ParseStatus)),
		"notes":            nullIfEmpty(input.Notes),
		"created_at":       now,
		"updated_at":       now,
	}
	query := `INSERT INTO grab_samples
		(site, sample_id, extracted_at, arrived_at, sample_taken_by, raw_file_name, storage_provider, storage_bucket, storage_key, file_url, parse_status, notes, created_at, updated_at)
		VALUES (:site, :sample_id, :extracted_at, :arrived_at, :sample_taken_by, :raw_file_name, :storage_provider, :storage_bucket, :storage_key, :file_url, :parse_status, :notes, :created_at, :updated_at)`
	if s.Driver == "postgres" {
		query += " RETURNING id"
	}
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return GrabSample{}, fmt.Errorf("insert grab_sample: %w", err)
	}
	query = s.DB.Rebind(query)
	var id int64
	if s.Driver == "postgres" {
		if err := s.DB.GetContext(ctx, &id, query, params...); err != nil {
			return GrabSample{}, fmt.Errorf("insert grab_sample: %w", err)
		}
	} else {
		res, err := s.DB.ExecContext(ctx, query, params...)
		if err != nil {
			return GrabSample{}, fmt.Errorf("insert grab_sample: %w", err)
		}
		id, err = res.LastInsertId()
		if err != nil {
			return GrabSample{}, fmt.Errorf("insert grab_sample: %w", err)
		}
	}
	return s.GetGrabSample(ctx, args["site"].(string), id)
}

func (s *Store) GetGrabSample(ctx context.Context, site string, id int64) (GrabSample, error) {
	if s == nil {
		return GrabSample{}, fmt.Errorf("store not configured")
	}
	query := `SELECT id, site, sample_id, extracted_at, arrived_at, sample_taken_by, raw_file_name, storage_provider, storage_bucket, storage_key, file_url, parse_status, notes, created_at, updated_at
		FROM grab_samples WHERE site = :site AND id = :id`
	args := map[string]any{"site": strings.ToLower(strings.TrimSpace(site)), "id": id}
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return GrabSample{}, fmt.Errorf("get grab_sample: %w", err)
	}
	query = s.DB.Rebind(query)
	var row grabSampleRow
	if err := s.DB.GetContext(ctx, &row, query, params...); err != nil {
		return GrabSample{}, err
	}
	return row.toGrabSample(), nil
}

func (s *Store) ListGrabSamples(ctx context.Context, opts ListGrabSamples) ([]GrabSample, error) {
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
		"site":   strings.ToLower(strings.TrimSpace(opts.Site)),
		"limit":  limit,
		"offset": offset,
	}
	query := `SELECT id, site, sample_id, extracted_at, arrived_at, sample_taken_by, raw_file_name, storage_provider, storage_bucket, storage_key, file_url, parse_status, notes, created_at, updated_at
		FROM grab_samples WHERE site = :site`
	if q := strings.TrimSpace(opts.Query); q != "" {
		args["q"] = "%" + strings.ToLower(q) + "%"
		query += ` AND (
			LOWER(sample_id) LIKE :q OR
			LOWER(COALESCE(sample_taken_by, '')) LIKE :q OR
			LOWER(COALESCE(raw_file_name, '')) LIKE :q OR
			LOWER(COALESCE(storage_key, '')) LIKE :q OR
			LOWER(COALESCE(notes, '')) LIKE :q
		)`
	}
	query += " ORDER BY COALESCE(extracted_at, created_at) DESC, id DESC LIMIT :limit OFFSET :offset"
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return nil, fmt.Errorf("list grab_samples: %w", err)
	}
	query = s.DB.Rebind(query)
	var rows []grabSampleRow
	if err := s.DB.SelectContext(ctx, &rows, query, params...); err != nil {
		return nil, fmt.Errorf("list grab_samples: %w", err)
	}
	out := make([]GrabSample, 0, len(rows))
	for _, row := range rows {
		out = append(out, row.toGrabSample())
	}
	return out, nil
}

func (s *Store) CountGrabSamples(ctx context.Context, opts ListGrabSamples) (int, error) {
	if s == nil {
		return 0, fmt.Errorf("store not configured")
	}
	args := map[string]any{
		"site": strings.ToLower(strings.TrimSpace(opts.Site)),
	}
	query := `SELECT COUNT(1) FROM grab_samples WHERE site = :site`
	if q := strings.TrimSpace(opts.Query); q != "" {
		args["q"] = "%" + strings.ToLower(q) + "%"
		query += ` AND (
			LOWER(sample_id) LIKE :q OR
			LOWER(COALESCE(sample_taken_by, '')) LIKE :q OR
			LOWER(COALESCE(raw_file_name, '')) LIKE :q OR
			LOWER(COALESCE(storage_key, '')) LIKE :q OR
			LOWER(COALESCE(notes, '')) LIKE :q
		)`
	}
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return 0, fmt.Errorf("count grab_samples: %w", err)
	}
	query = s.DB.Rebind(query)
	var total int
	if err := s.DB.GetContext(ctx, &total, query, params...); err != nil {
		return 0, fmt.Errorf("count grab_samples: %w", err)
	}
	return total, nil
}

func (s *Store) UpdateGrabSample(ctx context.Context, site string, id int64, input UpdateGrabSample) (GrabSample, error) {
	if s == nil {
		return GrabSample{}, fmt.Errorf("store not configured")
	}
	assignments := []string{"updated_at = :updated_at"}
	args := map[string]any{
		"site":       strings.ToLower(strings.TrimSpace(site)),
		"id":         id,
		"updated_at": time.Now().UTC(),
	}
	if input.ExtractedAt != nil {
		assignments = append(assignments, "extracted_at = :extracted_at")
		args["extracted_at"] = *input.ExtractedAt
	}
	if input.ArrivedAt != nil {
		assignments = append(assignments, "arrived_at = :arrived_at")
		args["arrived_at"] = *input.ArrivedAt
	}
	if input.SampleTakenBy != nil {
		assignments = append(assignments, "sample_taken_by = :sample_taken_by")
		args["sample_taken_by"] = nullIfEmpty(*input.SampleTakenBy)
	}
	if input.RawFileName != nil {
		assignments = append(assignments, "raw_file_name = :raw_file_name")
		args["raw_file_name"] = nullIfEmpty(*input.RawFileName)
	}
	if input.StorageProvider != nil {
		assignments = append(assignments, "storage_provider = :storage_provider")
		args["storage_provider"] = nullIfEmpty(*input.StorageProvider)
	}
	if input.StorageBucket != nil {
		assignments = append(assignments, "storage_bucket = :storage_bucket")
		args["storage_bucket"] = nullIfEmpty(*input.StorageBucket)
	}
	if input.StorageKey != nil {
		assignments = append(assignments, "storage_key = :storage_key")
		args["storage_key"] = nullIfEmpty(*input.StorageKey)
	}
	if input.FileURL != nil {
		assignments = append(assignments, "file_url = :file_url")
		args["file_url"] = nullIfEmpty(*input.FileURL)
	}
	if input.ParseStatus != nil {
		assignments = append(assignments, "parse_status = :parse_status")
		args["parse_status"] = nullIfEmpty(defaultParseStatus(*input.ParseStatus))
	}
	if input.Notes != nil {
		assignments = append(assignments, "notes = :notes")
		args["notes"] = nullIfEmpty(*input.Notes)
	}
	if len(assignments) == 1 {
		return s.GetGrabSample(ctx, site, id)
	}
	query := `UPDATE grab_samples SET ` + strings.Join(assignments, ", ") + ` WHERE site = :site AND id = :id`
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return GrabSample{}, fmt.Errorf("update grab_sample: %w", err)
	}
	query = s.DB.Rebind(query)
	res, err := s.DB.ExecContext(ctx, query, params...)
	if err != nil {
		return GrabSample{}, fmt.Errorf("update grab_sample: %w", err)
	}
	if rows, _ := res.RowsAffected(); rows == 0 {
		return GrabSample{}, sql.ErrNoRows
	}
	return s.GetGrabSample(ctx, site, id)
}

func (s *Store) DeleteGrabSample(ctx context.Context, site string, id int64) error {
	if s == nil {
		return fmt.Errorf("store not configured")
	}
	query := `DELETE FROM grab_samples WHERE site = :site AND id = :id`
	args := map[string]any{"site": strings.ToLower(strings.TrimSpace(site)), "id": id}
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return fmt.Errorf("delete grab_sample: %w", err)
	}
	query = s.DB.Rebind(query)
	res, err := s.DB.ExecContext(ctx, query, params...)
	if err != nil {
		return fmt.Errorf("delete grab_sample: %w", err)
	}
	if rows, _ := res.RowsAffected(); rows == 0 {
		return sql.ErrNoRows
	}
	return nil
}

func (r grabSampleRow) toGrabSample() GrabSample {
	out := GrabSample{
		ID:              r.ID,
		Site:            r.Site,
		SampleID:        r.SampleID,
		SampleTakenBy:   nullableString(r.SampleTakenBy),
		RawFileName:     nullableString(r.RawFileName),
		StorageProvider: nullableString(r.StorageProvider),
		StorageBucket:   nullableString(r.StorageBucket),
		StorageKey:      nullableString(r.StorageKey),
		FileURL:         nullableString(r.FileURL),
		ParseStatus:     nullableString(r.ParseStatus),
		Notes:           nullableString(r.Notes),
		CreatedAt:       r.CreatedAt,
		UpdatedAt:       r.UpdatedAt,
	}
	if r.ExtractedAt.Valid {
		t := r.ExtractedAt.Time.UTC()
		out.ExtractedAt = &t
	}
	if r.ArrivedAt.Valid {
		t := r.ArrivedAt.Time.UTC()
		out.ArrivedAt = &t
	}
	return out
}

func nullableString(value sql.NullString) string {
	if value.Valid {
		return value.String
	}
	return ""
}

func nullIfEmpty(value string) any {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil
	}
	return value
}

func defaultParseStatus(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return "pending"
	}
	return value
}
