package reports

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

type ReportUser struct {
	Email string `json:"email"`
	Name  string `json:"name,omitempty"`
	Sub   string `json:"sub,omitempty"`
}

type OperatorReport struct {
	ID        int64       `json:"id"`
	Site      string      `json:"site"`
	Title     string      `json:"title"`
	Body      string      `json:"body"`
	Status    string      `json:"status"`
	Severity  string      `json:"severity,omitempty"`
	Tags      []string    `json:"tags,omitempty"`
	CreatedAt time.Time   `json:"created_at"`
	UpdatedAt time.Time   `json:"updated_at"`
	CreatedBy *ReportUser `json:"created_by,omitempty"`
}

type CreateOperatorReport struct {
	Site           string
	Title          string
	Body           string
	Status         string
	Severity       string
	Tags           []string
	CreatedByEmail string
	CreatedByName  string
	CreatedBySub   string
}

type UpdateOperatorReport struct {
	Title    *string
	Body     *string
	Status   *string
	Severity *string
	Tags     *[]string
}

type ListOperatorReports struct {
	Site   string
	Status string
	Query  string
	Limit  int
	Offset int
}

type operatorReportRow struct {
	ID             int64          `db:"id"`
	Site           string         `db:"site"`
	Title          string         `db:"title"`
	Body           string         `db:"body"`
	Status         string         `db:"status"`
	Severity       sql.NullString `db:"severity"`
	Tags           sql.NullString `db:"tags"`
	CreatedAt      time.Time      `db:"created_at"`
	UpdatedAt      time.Time      `db:"updated_at"`
	CreatedByEmail sql.NullString `db:"created_by_email"`
	CreatedByName  sql.NullString `db:"created_by_name"`
	CreatedBySub   sql.NullString `db:"created_by_sub"`
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
		create = `CREATE TABLE IF NOT EXISTS operator_reports (
			id BIGSERIAL PRIMARY KEY,
			site TEXT NOT NULL,
			title TEXT NOT NULL,
			body TEXT NOT NULL,
			status TEXT NOT NULL,
			severity TEXT,
			tags TEXT,
			created_at TIMESTAMPTZ NOT NULL,
			updated_at TIMESTAMPTZ NOT NULL,
			created_by_email TEXT,
			created_by_name TEXT,
			created_by_sub TEXT
		)`
	default:
		create = `CREATE TABLE IF NOT EXISTS operator_reports (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			site TEXT NOT NULL,
			title TEXT NOT NULL,
			body TEXT NOT NULL,
			status TEXT NOT NULL,
			severity TEXT,
			tags TEXT,
			created_at TIMESTAMP NOT NULL,
			updated_at TIMESTAMP NOT NULL,
			created_by_email TEXT,
			created_by_name TEXT,
			created_by_sub TEXT
		)`
	}
	if _, err := s.DB.ExecContext(ctx, create); err != nil {
		return fmt.Errorf("create operator_reports: %w", err)
	}

	idx := "CREATE INDEX IF NOT EXISTS operator_reports_site_created_at_idx ON operator_reports(site, created_at DESC)"
	if _, err := s.DB.ExecContext(ctx, idx); err != nil {
		return fmt.Errorf("create operator_reports index: %w", err)
	}
	idxStatus := "CREATE INDEX IF NOT EXISTS operator_reports_site_status_idx ON operator_reports(site, status)"
	if _, err := s.DB.ExecContext(ctx, idxStatus); err != nil {
		return fmt.Errorf("create operator_reports status index: %w", err)
	}
	return nil
}

func (s *Store) CreateOperatorReport(ctx context.Context, input CreateOperatorReport) (OperatorReport, error) {
	if s == nil {
		return OperatorReport{}, fmt.Errorf("store not configured")
	}
	now := time.Now().UTC()
	status := strings.TrimSpace(input.Status)
	if status == "" {
		status = "open"
	}

	tagsRaw, err := encodeTags(input.Tags)
	if err != nil {
		return OperatorReport{}, err
	}

	args := map[string]any{
		"site":             strings.ToLower(strings.TrimSpace(input.Site)),
		"title":            strings.TrimSpace(input.Title),
		"body":             strings.TrimSpace(input.Body),
		"status":           status,
		"severity":         nullIfEmpty(strings.TrimSpace(input.Severity)),
		"tags":             tagsRaw,
		"created_at":       now,
		"updated_at":       now,
		"created_by_email": nullIfEmpty(strings.TrimSpace(input.CreatedByEmail)),
		"created_by_name":  nullIfEmpty(strings.TrimSpace(input.CreatedByName)),
		"created_by_sub":   nullIfEmpty(strings.TrimSpace(input.CreatedBySub)),
	}

	query := `INSERT INTO operator_reports
		(site, title, body, status, severity, tags, created_at, updated_at, created_by_email, created_by_name, created_by_sub)
		VALUES (:site, :title, :body, :status, :severity, :tags, :created_at, :updated_at, :created_by_email, :created_by_name, :created_by_sub)`
	if s.Driver == "postgres" {
		query += " RETURNING id"
	}

	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return OperatorReport{}, fmt.Errorf("insert operator_report: %w", err)
	}
	query = s.DB.Rebind(query)

	var id int64
	if s.Driver == "postgres" {
		if err := s.DB.GetContext(ctx, &id, query, params...); err != nil {
			return OperatorReport{}, fmt.Errorf("insert operator_report: %w", err)
		}
	} else {
		res, err := s.DB.ExecContext(ctx, query, params...)
		if err != nil {
			return OperatorReport{}, fmt.Errorf("insert operator_report: %w", err)
		}
		id, err = res.LastInsertId()
		if err != nil {
			return OperatorReport{}, fmt.Errorf("insert operator_report: %w", err)
		}
	}

	return s.GetOperatorReport(ctx, args["site"].(string), id)
}

func (s *Store) GetOperatorReport(ctx context.Context, site string, id int64) (OperatorReport, error) {
	if s == nil {
		return OperatorReport{}, fmt.Errorf("store not configured")
	}
	query := `SELECT id, site, title, body, status, severity, tags, created_at, updated_at, created_by_email, created_by_name, created_by_sub
		FROM operator_reports WHERE site = :site AND id = :id`
	args := map[string]any{"site": strings.ToLower(strings.TrimSpace(site)), "id": id}
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return OperatorReport{}, fmt.Errorf("get operator_report: %w", err)
	}
	query = s.DB.Rebind(query)
	var row operatorReportRow
	if err := s.DB.GetContext(ctx, &row, query, params...); err != nil {
		return OperatorReport{}, err
	}
	return row.toReport(), nil
}

func (s *Store) ListOperatorReports(ctx context.Context, opts ListOperatorReports) ([]OperatorReport, error) {
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
	query := `SELECT id, site, title, body, status, severity, tags, created_at, updated_at, created_by_email, created_by_name, created_by_sub
		FROM operator_reports WHERE site = :site`
	if strings.TrimSpace(opts.Status) != "" {
		query += " AND status = :status"
		args["status"] = strings.TrimSpace(opts.Status)
	}
	if q := strings.TrimSpace(opts.Query); q != "" {
		args["q"] = "%" + strings.ToLower(q) + "%"
		query += ` AND (
			LOWER(title) LIKE :q OR
			LOWER(body) LIKE :q OR
			LOWER(COALESCE(created_by_name, '')) LIKE :q OR
			LOWER(COALESCE(created_by_email, '')) LIKE :q
		)`
	}
	query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return nil, fmt.Errorf("list operator_reports: %w", err)
	}
	query = s.DB.Rebind(query)

	var rows []operatorReportRow
	if err := s.DB.SelectContext(ctx, &rows, query, params...); err != nil {
		return nil, err
	}
	out := make([]OperatorReport, 0, len(rows))
	for _, row := range rows {
		out = append(out, row.toReport())
	}
	return out, nil
}

func (s *Store) CountOperatorReports(ctx context.Context, opts ListOperatorReports) (int, error) {
	if s == nil {
		return 0, fmt.Errorf("store not configured")
	}
	args := map[string]any{
		"site": strings.ToLower(strings.TrimSpace(opts.Site)),
	}
	query := `SELECT COUNT(*) FROM operator_reports WHERE site = :site`
	if strings.TrimSpace(opts.Status) != "" {
		query += " AND status = :status"
		args["status"] = strings.TrimSpace(opts.Status)
	}
	if q := strings.TrimSpace(opts.Query); q != "" {
		args["q"] = "%" + strings.ToLower(q) + "%"
		query += ` AND (
			LOWER(title) LIKE :q OR
			LOWER(body) LIKE :q OR
			LOWER(COALESCE(created_by_name, '')) LIKE :q OR
			LOWER(COALESCE(created_by_email, '')) LIKE :q
		)`
	}
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return 0, fmt.Errorf("count operator_reports: %w", err)
	}
	query = s.DB.Rebind(query)
	var total int
	if err := s.DB.GetContext(ctx, &total, query, params...); err != nil {
		return 0, fmt.Errorf("count operator_reports: %w", err)
	}
	return total, nil
}

func (s *Store) UpdateOperatorReport(ctx context.Context, site string, id int64, update UpdateOperatorReport) (OperatorReport, error) {
	if s == nil {
		return OperatorReport{}, fmt.Errorf("store not configured")
	}
	sets := []string{}
	args := map[string]any{
		"site": strings.ToLower(strings.TrimSpace(site)),
		"id":   id,
	}
	if update.Title != nil {
		sets = append(sets, "title = :title")
		args["title"] = strings.TrimSpace(*update.Title)
	}
	if update.Body != nil {
		sets = append(sets, "body = :body")
		args["body"] = strings.TrimSpace(*update.Body)
	}
	if update.Status != nil {
		sets = append(sets, "status = :status")
		args["status"] = strings.TrimSpace(*update.Status)
	}
	if update.Severity != nil {
		sets = append(sets, "severity = :severity")
		args["severity"] = nullIfEmpty(strings.TrimSpace(*update.Severity))
	}
	if update.Tags != nil {
		tagsRaw, err := encodeTags(*update.Tags)
		if err != nil {
			return OperatorReport{}, err
		}
		sets = append(sets, "tags = :tags")
		args["tags"] = tagsRaw
	}
	if len(sets) == 0 {
		return OperatorReport{}, fmt.Errorf("no fields to update")
	}

	args["updated_at"] = time.Now().UTC()
	sets = append(sets, "updated_at = :updated_at")

	query := fmt.Sprintf("UPDATE operator_reports SET %s WHERE site = :site AND id = :id", strings.Join(sets, ", "))
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return OperatorReport{}, fmt.Errorf("update operator_report: %w", err)
	}
	query = s.DB.Rebind(query)
	res, err := s.DB.ExecContext(ctx, query, params...)
	if err != nil {
		return OperatorReport{}, fmt.Errorf("update operator_report: %w", err)
	}
	affected, err := res.RowsAffected()
	if err == nil && affected == 0 {
		return OperatorReport{}, sql.ErrNoRows
	}
	return s.GetOperatorReport(ctx, args["site"].(string), id)
}

func (s *Store) DeleteOperatorReport(ctx context.Context, site string, id int64) error {
	if s == nil {
		return fmt.Errorf("store not configured")
	}
	query := `DELETE FROM operator_reports WHERE site = :site AND id = :id`
	args := map[string]any{"site": strings.ToLower(strings.TrimSpace(site)), "id": id}
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return fmt.Errorf("delete operator_report: %w", err)
	}
	query = s.DB.Rebind(query)
	res, err := s.DB.ExecContext(ctx, query, params...)
	if err != nil {
		return fmt.Errorf("delete operator_report: %w", err)
	}
	affected, err := res.RowsAffected()
	if err == nil && affected == 0 {
		return sql.ErrNoRows
	}
	return nil
}

func (r operatorReportRow) toReport() OperatorReport {
	report := OperatorReport{
		ID:        r.ID,
		Site:      r.Site,
		Title:     r.Title,
		Body:      r.Body,
		Status:    r.Status,
		Severity:  r.Severity.String,
		Tags:      decodeTags(r.Tags),
		CreatedAt: r.CreatedAt,
		UpdatedAt: r.UpdatedAt,
	}
	if r.CreatedByEmail.Valid || r.CreatedByName.Valid || r.CreatedBySub.Valid {
		report.CreatedBy = &ReportUser{
			Email: r.CreatedByEmail.String,
			Name:  r.CreatedByName.String,
			Sub:   r.CreatedBySub.String,
		}
	}
	return report
}

func encodeTags(tags []string) (string, error) {
	if len(tags) == 0 {
		return "", nil
	}
	raw, err := json.Marshal(tags)
	if err != nil {
		return "", fmt.Errorf("encode tags: %w", err)
	}
	return string(raw), nil
}

func decodeTags(raw sql.NullString) []string {
	if !raw.Valid {
		return nil
	}
	text := strings.TrimSpace(raw.String)
	if text == "" {
		return nil
	}
	var tags []string
	if err := json.Unmarshal([]byte(text), &tags); err != nil {
		return nil
	}
	return tags
}

func nullIfEmpty(v string) sql.NullString {
	if strings.TrimSpace(v) == "" {
		return sql.NullString{}
	}
	return sql.NullString{String: v, Valid: true}
}
