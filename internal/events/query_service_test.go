package events

import (
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
)

func TestBuildSQLSQLite_AllMatch(t *testing.T) {
	req := QueryRequest{
		Match: "all",
		Conditions: []Condition{
			{Field: "alarm", Op: "eq", Value: true},
			{Field: "permeateflow", Op: "gt", Value: 10.5},
		},
		MaxResults: 123,
	}
	start := time.Date(2026, 2, 20, 9, 0, 0, 0, time.UTC)
	end := time.Date(2026, 2, 20, 10, 0, 0, 0, time.UTC)
	allowed := map[string]struct{}{
		"alarm":        {},
		"permeateflow": {},
	}

	sqlText, args, err := buildSQL("sqlite3", "bluerock_plc_data", req, start, end, allowed)
	if err != nil {
		t.Fatalf("buildSQL returned error: %v", err)
	}

	if !strings.Contains(sqlText, "datetime(plctime) BETWEEN datetime(?) AND datetime(?)") {
		t.Fatalf("sqlite time clause missing, sql=%s", sqlText)
	}
	if !strings.Contains(sqlText, "(alarm = ? AND permeateflow > ?)") {
		t.Fatalf("condition clause mismatch, sql=%s", sqlText)
	}
	if !strings.Contains(sqlText, "LIMIT ?") {
		t.Fatalf("limit placeholder missing, sql=%s", sqlText)
	}
	if len(args) != 5 {
		t.Fatalf("expected 5 args, got %d (%v)", len(args), args)
	}
}

func TestBuildSQLPostgres_AnyMatch(t *testing.T) {
	req := QueryRequest{
		Match: "any",
		Conditions: []Condition{
			{Field: "alarm", Op: "eq", Value: true},
			{Field: "warnword0", Op: "gt", Value: 0},
		},
		MaxResults: 50,
	}
	start := time.Date(2026, 2, 20, 9, 0, 0, 0, time.UTC)
	end := time.Date(2026, 2, 20, 10, 0, 0, 0, time.UTC)
	allowed := map[string]struct{}{
		"alarm":     {},
		"warnword0": {},
	}

	sqlText, args, err := buildSQL("postgres", "bluerock_plc_data", req, start, end, allowed)
	if err != nil {
		t.Fatalf("buildSQL returned error: %v", err)
	}

	if !strings.Contains(sqlText, "plctime BETWEEN ? AND ?") {
		t.Fatalf("postgres time clause mismatch, sql=%s", sqlText)
	}
	if !strings.Contains(sqlText, "(alarm = ? OR warnword0 > ?)") {
		t.Fatalf("OR condition clause mismatch, sql=%s", sqlText)
	}
	if len(args) != 5 {
		t.Fatalf("expected 5 args, got %d (%v)", len(args), args)
	}
}

func TestBuildSQLRejectsInvalidFieldAndOp(t *testing.T) {
	start := time.Date(2026, 2, 20, 9, 0, 0, 0, time.UTC)
	end := time.Date(2026, 2, 20, 10, 0, 0, 0, time.UTC)

	_, _, err := buildSQL("sqlite3", "bluerock_plc_data", QueryRequest{
		Match:      "all",
		Conditions: []Condition{{Field: "DROP TABLE", Op: "eq", Value: "x"}},
		MaxResults: 10,
	}, start, end, map[string]struct{}{"alarm": {}})
	if err == nil {
		t.Fatal("expected field validation error, got nil")
	}

	_, _, err = buildSQL("sqlite3", "bluerock_plc_data", QueryRequest{
		Match:      "all",
		Conditions: []Condition{{Field: "alarm", Op: "like", Value: "x"}},
		MaxResults: 10,
	}, start, end, map[string]struct{}{"alarm": {}})
	if err == nil {
		t.Fatal("expected op validation error, got nil")
	}
}

func TestQuerySiteEventsSQLite_ReturnsInterestingTimestamps(t *testing.T) {
	dbPath := filepath.Join(t.TempDir(), "events_test.db")
	client, err := database.NewSQLiteClient(dbPath)
	if err != nil {
		t.Fatalf("NewSQLiteClient error: %v", err)
	}

	schema := `
CREATE TABLE IF NOT EXISTS bluerock_plc_values (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plctime TEXT NOT NULL,
  alarm INTEGER NOT NULL,
  permeateflow REAL NOT NULL
);`
	if _, err := client.DB.Exec(schema); err != nil {
		t.Fatalf("create table error: %v", err)
	}

	rows := []struct {
		t  string
		al int
		pf float64
	}{
		{"2026-02-20T09:00:00Z", 1, 12.0},
		{"2026-02-20T09:00:30Z", 1, 13.0},
		{"2026-02-20T09:01:30Z", 1, 14.0},
		{"2026-02-20T09:02:30Z", 0, 15.0}, // filtered by alarm condition
	}
	for _, r := range rows {
		if _, err := client.DB.Exec(
			"INSERT INTO bluerock_plc_values(plctime, alarm, permeateflow) VALUES (?, ?, ?)",
			r.t, r.al, r.pf,
		); err != nil {
			t.Fatalf("insert error: %v", err)
		}
	}

	svc := &QueryService{db: client.DB, driver: "sqlite3"}
	res, err := svc.QuerySiteEvents("bluerock", QueryRequest{
		TimeWindow: TimeWindow{
			Start: "2026-02-20T08:59:00Z",
			End:   "2026-02-20T09:03:00Z",
		},
		Match: "all",
		Conditions: []Condition{
			{Field: "alarm", Op: "eq", Value: true},
			{Field: "permeateflow", Op: "gt", Value: 10},
		},
		MaxResults:    100,
		MinGapSeconds: 60,
	})
	if err != nil {
		t.Fatalf("QuerySiteEvents returned error: %v", err)
	}

	// First two are 30s apart; min_gap filters one of them.
	if len(res.Timestamps) != 2 {
		t.Fatalf("expected 2 timestamps, got %d (%v)", len(res.Timestamps), res.Timestamps)
	}
	if res.Timestamps[0] != "2026-02-20T09:00:00Z" {
		t.Fatalf("unexpected first timestamp: %s", res.Timestamps[0])
	}
	if res.Timestamps[1] != "2026-02-20T09:01:30Z" {
		t.Fatalf("unexpected second timestamp: %s", res.Timestamps[1])
	}
}
