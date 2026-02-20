package events

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/jmoiron/sqlx"
)

type Condition struct {
	Field string `json:"field"`
	Op    string `json:"op"` // eq, neq, gt, gte, lt, lte
	Value any    `json:"value"`
}

type TimeWindow struct {
	Start string `json:"start"`
	End   string `json:"end"`
}

type QueryRequest struct {
	TimeWindow    TimeWindow  `json:"time_window"`
	Match         string      `json:"match"` // all | any
	Conditions    []Condition `json:"conditions"`
	MaxResults    int         `json:"max_results"`
	MinGapSeconds int         `json:"min_gap_seconds"`
}

type QueryResult struct {
	Timestamps []string `json:"timestamps"`
	SQL        string   `json:"sql,omitempty"`
}

type QueryService struct {
	db     *sqlx.DB
	driver string
}

func NewQueryServiceFromEnv() (*QueryService, error) {
	if pg := strings.TrimSpace(os.Getenv("DATABASE_URL")); pg != "" {
		client, err := database.NewPostgresClient(pg)
		if err != nil {
			return nil, err
		}
		return &QueryService{db: client.DB, driver: client.Driver}, nil
	}
	path := strings.TrimSpace(os.Getenv("SQLITE_PATH"))
	if path == "" {
		path = "./data/svwatergo.db"
	}
	client, err := database.NewSQLiteClient(path)
	if err != nil {
		return nil, err
	}
	return &QueryService{db: client.DB, driver: client.Driver}, nil
}

func (s *QueryService) QuerySiteEvents(site string, req QueryRequest) (QueryResult, error) {
	if s == nil || s.db == nil {
		return QueryResult{}, fmt.Errorf("query service not configured")
	}
	table, ok := siteTable(site)
	if !ok {
		return QueryResult{}, fmt.Errorf("unsupported site: %s", site)
	}

	start, err := time.Parse(time.RFC3339, req.TimeWindow.Start)
	if err != nil {
		return QueryResult{}, fmt.Errorf("invalid start")
	}
	end, err := time.Parse(time.RFC3339, req.TimeWindow.End)
	if err != nil {
		return QueryResult{}, fmt.Errorf("invalid end")
	}
	if !start.Before(end) {
		return QueryResult{}, fmt.Errorf("start must be before end")
	}
	if len(req.Conditions) == 0 {
		return QueryResult{}, fmt.Errorf("at least one condition is required")
	}
	if req.MaxResults <= 0 {
		req.MaxResults = 500
	}
	if req.MaxResults > 5000 {
		req.MaxResults = 5000
	}
	if req.Match == "" {
		req.Match = "all"
	}
	if req.Match != "all" && req.Match != "any" {
		return QueryResult{}, fmt.Errorf("match must be all or any")
	}

	allowed, err := s.allowedColumns(table)
	if err != nil {
		return QueryResult{}, err
	}
	sqlText, args, err := buildSQL(s.driver, table, req, start, end, allowed)
	if err != nil {
		return QueryResult{}, err
	}

	type row struct {
		PLCTime any `db:"plctime"`
	}
	out := []row{}
	if err := s.db.Select(&out, sqlText, args...); err != nil {
		return QueryResult{}, err
	}

	minGap := time.Duration(req.MinGapSeconds) * time.Second
	timestamps := make([]string, 0, len(out))
	var last time.Time
	for _, r := range out {
		ts, ok := normalizeTime(r.PLCTime)
		if !ok {
			continue
		}
		if !last.IsZero() && minGap > 0 && ts.Sub(last) < minGap {
			continue
		}
		last = ts
		timestamps = append(timestamps, ts.UTC().Format(time.RFC3339))
	}

	return QueryResult{Timestamps: timestamps, SQL: sqlText}, nil
}

func buildSQL(driver, table string, req QueryRequest, start, end time.Time, allowed map[string]struct{}) (string, []any, error) {
	args := make([]any, 0, len(req.Conditions)+3)
	whereParts := []string{}

	timeClause := "plctime BETWEEN ? AND ?"
	if driver == "sqlite3" {
		timeClause = "datetime(plctime) BETWEEN datetime(?) AND datetime(?)"
	}
	whereParts = append(whereParts, timeClause)
	args = append(args, start.UTC().Format(time.RFC3339Nano), end.UTC().Format(time.RFC3339Nano))

	condParts := make([]string, 0, len(req.Conditions))
	for _, c := range req.Conditions {
		field := strings.ToLower(strings.TrimSpace(c.Field))
		if _, ok := allowed[field]; !ok {
			return "", nil, fmt.Errorf("field not allowed: %s", c.Field)
		}
		opSQL, err := sqlOp(c.Op)
		if err != nil {
			return "", nil, err
		}
		condParts = append(condParts, fmt.Sprintf("%s %s ?", field, opSQL))
		args = append(args, normalizeValue(c.Value))
	}
	glue := " AND "
	if req.Match == "any" {
		glue = " OR "
	}
	whereParts = append(whereParts, "("+strings.Join(condParts, glue)+")")

	q := fmt.Sprintf(
		"SELECT plctime FROM %s WHERE %s ORDER BY %s ASC LIMIT ?",
		table,
		strings.Join(whereParts, " AND "),
		orderByTime(driver),
	)
	args = append(args, req.MaxResults)
	return q, args, nil
}

func sqlOp(op string) (string, error) {
	switch strings.ToLower(strings.TrimSpace(op)) {
	case "eq":
		return "=", nil
	case "neq":
		return "!=", nil
	case "gt":
		return ">", nil
	case "gte":
		return ">=", nil
	case "lt":
		return "<", nil
	case "lte":
		return "<=", nil
	default:
		return "", fmt.Errorf("unsupported op: %s", op)
	}
}

func orderByTime(driver string) string {
	if driver == "sqlite3" {
		return "datetime(plctime)"
	}
	return "plctime"
}

func (s *QueryService) allowedColumns(table string) (map[string]struct{}, error) {
	out := map[string]struct{}{}
	if s.driver == "sqlite3" {
		type col struct {
			Name string `db:"name"`
		}
		cols := []col{}
		// Query only the name column to avoid PRAGMA extra columns causing strict scan errors.
		query := fmt.Sprintf("SELECT name FROM pragma_table_info('%s')", table)
		if err := s.db.Select(&cols, query); err != nil {
			return nil, err
		}
		for _, c := range cols {
			out[strings.ToLower(c.Name)] = struct{}{}
		}
		return out, nil
	}

	type col struct {
		ColumnName string `db:"column_name"`
	}
	cols := []col{}
	if err := s.db.Select(&cols, "SELECT column_name FROM information_schema.columns WHERE table_name = $1", table); err != nil {
		return nil, err
	}
	for _, c := range cols {
		out[strings.ToLower(c.ColumnName)] = struct{}{}
	}
	return out, nil
}

func normalizeValue(v any) any {
	switch t := v.(type) {
	case bool:
		return t
	case float64, float32, int, int64, int32, uint, uint32, uint64:
		return t
	case string:
		s := strings.TrimSpace(t)
		if strings.EqualFold(s, "true") {
			return true
		}
		if strings.EqualFold(s, "false") {
			return false
		}
		if i, err := strconv.ParseInt(s, 10, 64); err == nil {
			return i
		}
		if f, err := strconv.ParseFloat(s, 64); err == nil {
			return f
		}
		return s
	default:
		return fmt.Sprintf("%v", v)
	}
}

func normalizeTime(v any) (time.Time, bool) {
	switch t := v.(type) {
	case time.Time:
		return t.UTC(), true
	case string:
		if parsed, err := time.Parse(time.RFC3339Nano, t); err == nil {
			return parsed.UTC(), true
		}
		if parsed, err := time.Parse(time.RFC3339, t); err == nil {
			return parsed.UTC(), true
		}
	case []byte:
		return normalizeTime(string(t))
	}
	return time.Time{}, false
}

func siteTable(site string) (string, bool) {
	switch strings.ToLower(strings.TrimSpace(site)) {
	case "bluerock":
		return "bluerock_plc_data", true
	case "pryorfarm":
		return "pryorfarm_plc_data", true
	case "santateresa":
		return "santateresa_plc_data", true
	default:
		return "", false
	}
}
