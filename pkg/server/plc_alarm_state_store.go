package server

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/jmoiron/sqlx"
)

type plcAlarmStateStore struct {
	DB     *sqlx.DB
	Driver string
}

type plcAlarmStateRow struct {
	Site               string       `db:"site"`
	AlarmActive        int          `db:"alarm_active"`
	AlarmKey           string       `db:"alarm_key"`
	LastAlertAt        sql.NullTime `db:"last_alert_at"`
	LastSeenAt         time.Time    `db:"last_seen_at"`
	MessageCount       int64        `db:"message_count"`
	IncidentReportedAt sql.NullTime `db:"incident_reported_at"`
	IncidentResolvedAt sql.NullTime `db:"incident_resolved_at"`
}

func newPLCAlarmStateStore(client *database.SQLXClient) *plcAlarmStateStore {
	if client == nil || client.DB == nil {
		return nil
	}
	return &plcAlarmStateStore{DB: client.DB, Driver: client.Driver}
}

func (s *plcAlarmStateStore) EnsureSchema(ctx context.Context) error {
	if s == nil {
		return nil
	}
	var ddl string
	switch s.Driver {
	case "postgres":
		ddl = `CREATE TABLE IF NOT EXISTS plc_alarm_alert_state (
			site TEXT PRIMARY KEY,
			alarm_active INTEGER NOT NULL,
			alarm_key TEXT NOT NULL,
			last_alert_at TIMESTAMPTZ NULL,
			last_seen_at TIMESTAMPTZ NOT NULL,
			message_count BIGINT NOT NULL DEFAULT 0,
			incident_reported_at TIMESTAMPTZ NULL,
			incident_resolved_at TIMESTAMPTZ NULL,
			updated_at TIMESTAMPTZ NOT NULL
		)`
	default:
		ddl = `CREATE TABLE IF NOT EXISTS plc_alarm_alert_state (
			site TEXT PRIMARY KEY,
			alarm_active INTEGER NOT NULL,
			alarm_key TEXT NOT NULL,
			last_alert_at TIMESTAMP NULL,
			last_seen_at TIMESTAMP NOT NULL,
			message_count INTEGER NOT NULL DEFAULT 0,
			incident_reported_at TIMESTAMP NULL,
			incident_resolved_at TIMESTAMP NULL,
			updated_at TIMESTAMP NOT NULL
		)`
	}
	if _, err := s.DB.ExecContext(ctx, ddl); err != nil {
		return fmt.Errorf("create plc_alarm_alert_state: %w", err)
	}
	idx := "CREATE INDEX IF NOT EXISTS plc_alarm_alert_state_active_idx ON plc_alarm_alert_state(alarm_active)"
	if _, err := s.DB.ExecContext(ctx, idx); err != nil {
		return fmt.Errorf("create plc_alarm_alert_state index: %w", err)
	}
	// Backfill columns for databases created before these fields were added.
	_, _ = s.DB.ExecContext(ctx, "ALTER TABLE plc_alarm_alert_state ADD COLUMN message_count INTEGER NOT NULL DEFAULT 0")
	_, _ = s.DB.ExecContext(ctx, "ALTER TABLE plc_alarm_alert_state ADD COLUMN incident_reported_at TIMESTAMP NULL")
	_, _ = s.DB.ExecContext(ctx, "ALTER TABLE plc_alarm_alert_state ADD COLUMN incident_resolved_at TIMESTAMP NULL")
	return nil
}

func (s *plcAlarmStateStore) Get(ctx context.Context, site string) (plcAlarmMonitorState, bool, error) {
	if s == nil {
		return plcAlarmMonitorState{}, false, nil
	}
	query := `SELECT site, alarm_active, alarm_key, last_alert_at, last_seen_at, message_count, incident_reported_at, incident_resolved_at
		FROM plc_alarm_alert_state WHERE site = :site`
	args := map[string]any{
		"site": strings.ToLower(strings.TrimSpace(site)),
	}
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return plcAlarmMonitorState{}, false, fmt.Errorf("prepare get plc alarm state: %w", err)
	}
	query = s.DB.Rebind(query)
	var row plcAlarmStateRow
	if err := s.DB.GetContext(ctx, &row, query, params...); err != nil {
		if err == sql.ErrNoRows {
			return plcAlarmMonitorState{}, false, nil
		}
		return plcAlarmMonitorState{}, false, fmt.Errorf("get plc alarm state: %w", err)
	}
	out := plcAlarmMonitorState{
		lastSeenTS:   row.LastSeenAt.UTC(),
		lastAlarmOn:  row.AlarmActive != 0,
		lastAlarmKey: strings.TrimSpace(row.AlarmKey),
		messageCount: row.MessageCount,
	}
	if row.LastAlertAt.Valid {
		out.lastAlertAt = row.LastAlertAt.Time.UTC()
	}
	if row.IncidentReportedAt.Valid {
		out.incidentReportedAt = row.IncidentReportedAt.Time.UTC()
	}
	if row.IncidentResolvedAt.Valid {
		out.incidentResolvedAt = row.IncidentResolvedAt.Time.UTC()
	}
	return out, true, nil
}

func (s *plcAlarmStateStore) Upsert(ctx context.Context, site string, st plcAlarmMonitorState) error {
	if s == nil {
		return nil
	}
	now := time.Now().UTC()
	var lastAlert any
	if st.lastAlertAt.IsZero() {
		lastAlert = nil
	} else {
		lastAlert = st.lastAlertAt.UTC()
	}
	var incidentReported any
	if st.incidentReportedAt.IsZero() {
		incidentReported = nil
	} else {
		incidentReported = st.incidentReportedAt.UTC()
	}
	var incidentResolved any
	if st.incidentResolvedAt.IsZero() {
		incidentResolved = nil
	} else {
		incidentResolved = st.incidentResolvedAt.UTC()
	}
	args := map[string]any{
		"site":                 strings.ToLower(strings.TrimSpace(site)),
		"alarm_active":         boolToInt(st.lastAlarmOn),
		"alarm_key":            strings.TrimSpace(st.lastAlarmKey),
		"last_alert_at":        lastAlert,
		"last_seen_at":         st.lastSeenTS.UTC(),
		"message_count":        st.messageCount,
		"incident_reported_at": incidentReported,
		"incident_resolved_at": incidentResolved,
		"updated_at":           now,
	}

	query := `INSERT INTO plc_alarm_alert_state
		(site, alarm_active, alarm_key, last_alert_at, last_seen_at, message_count, incident_reported_at, incident_resolved_at, updated_at)
		VALUES (:site, :alarm_active, :alarm_key, :last_alert_at, :last_seen_at, :message_count, :incident_reported_at, :incident_resolved_at, :updated_at)
		ON CONFLICT(site) DO UPDATE SET
			alarm_active = excluded.alarm_active,
			alarm_key = excluded.alarm_key,
			last_alert_at = excluded.last_alert_at,
			last_seen_at = excluded.last_seen_at,
			message_count = excluded.message_count,
			incident_reported_at = excluded.incident_reported_at,
			incident_resolved_at = excluded.incident_resolved_at,
			updated_at = excluded.updated_at`
	query, params, err := sqlx.Named(query, args)
	if err != nil {
		return fmt.Errorf("prepare upsert plc alarm state: %w", err)
	}
	query = s.DB.Rebind(query)
	if _, err := s.DB.ExecContext(ctx, query, params...); err != nil {
		return fmt.Errorf("upsert plc alarm state: %w", err)
	}
	return nil
}

func boolToInt(v bool) int {
	if v {
		return 1
	}
	return 0
}
