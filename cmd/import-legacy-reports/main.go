package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/cbaguilar/svwatergo/internal/reports"
	"github.com/jmoiron/sqlx"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

type config struct {
	mongoURI        string
	mongoDB         string
	mongoCollection string
	sqlDriver       string
	sqlDSN          string
	siteFilter      string
	limit           int
	dryRun          bool
	skipExisting    bool
	verbose         bool
}

func main() {
	cfg := parseFlags()
	if err := run(cfg); err != nil {
		log.Fatal(err)
	}
}

func parseFlags() config {
	cfg := config{}
	flag.StringVar(&cfg.mongoURI, "mongo-uri", strings.TrimSpace(os.Getenv("MONGO_URL")), "Mongo connection URI (defaults to MONGO_URL)")
	flag.StringVar(&cfg.mongoDB, "mongo-db", "waterapp_db", "Mongo database name")
	flag.StringVar(&cfg.mongoCollection, "mongo-collection", "adminMonitoring", "Mongo collection name")
	flag.StringVar(&cfg.sqlDriver, "sql-driver", defaultSQLDriver(), "SQL driver (postgres|sqlite3)")
	flag.StringVar(&cfg.sqlDSN, "sql-dsn", defaultSQLDSN(), "SQL DSN (defaults to DATABASE_URL for postgres)")
	flag.StringVar(&cfg.siteFilter, "site", "", "Optional site filter (bluerock|santateresa|pryorfarm)")
	flag.IntVar(&cfg.limit, "limit", 0, "Optional max docs to import")
	flag.BoolVar(&cfg.dryRun, "dry-run", true, "Validate/map only; do not insert rows")
	flag.BoolVar(&cfg.skipExisting, "skip-existing", true, "Skip rows already imported (match site + created_at + body)")
	flag.BoolVar(&cfg.verbose, "verbose", false, "Log each mapped/imported report")
	flag.Parse()
	return cfg
}

func defaultSQLDriver() string {
	if strings.TrimSpace(os.Getenv("DATABASE_URL")) != "" {
		return "postgres"
	}
	return ""
}

func defaultSQLDSN() string {
	return strings.TrimSpace(os.Getenv("DATABASE_URL"))
}

func run(cfg config) error {
	if cfg.mongoURI == "" {
		return fmt.Errorf("missing Mongo URI (set -mongo-uri or MONGO_URL)")
	}
	if cfg.sqlDriver == "" || cfg.sqlDSN == "" {
		return fmt.Errorf("missing SQL connection (set -sql-driver/-sql-dsn or DATABASE_URL)")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	sqlClient, err := openSQL(cfg.sqlDriver, cfg.sqlDSN)
	if err != nil {
		return fmt.Errorf("open sql: %w", err)
	}
	defer sqlClient.DB.Close()

	reportStore := reports.NewStore(sqlClient)
	if err := reportStore.EnsureSchema(ctx); err != nil {
		return fmt.Errorf("ensure operator_reports schema: %w", err)
	}

	mc, err := mongo.Connect(ctx, options.Client().ApplyURI(cfg.mongoURI))
	if err != nil {
		return fmt.Errorf("connect mongo: %w", err)
	}
	defer func() {
		cctx, ccancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer ccancel()
		_ = mc.Disconnect(cctx)
	}()

	coll := mc.Database(cfg.mongoDB).Collection(cfg.mongoCollection)
	filter := bson.M{}
	if strings.TrimSpace(cfg.siteFilter) != "" {
		// Legacy field is depLocation and often stored as lowercase labels.
		sf := normalizeSiteLabel(cfg.siteFilter)
		filter["depLocation"] = bson.M{"$in": []string{sf, prettyLegacySite(sf)}}
	}
	findOpts := options.Find().SetSort(bson.D{{Key: "timestamp", Value: 1}, {Key: "_id", Value: 1}})
	if cfg.limit > 0 {
		findOpts.SetLimit(int64(cfg.limit))
	}

	cur, err := coll.Find(ctx, filter, findOpts)
	if err != nil {
		return fmt.Errorf("query mongo reports: %w", err)
	}
	defer cur.Close(context.Background())

	var (
		seen       int
		imported   int
		skipped    int
		failed     int
		duplicates int
	)

	for cur.Next(context.Background()) {
		seen++
		var doc bson.M
		if err := cur.Decode(&doc); err != nil {
			failed++
			log.Printf("decode mongo doc #%d: %v", seen, err)
			continue
		}
		row, err := mapLegacyAdminMonitoringDoc(doc)
		if err != nil {
			failed++
			log.Printf("map mongo doc #%d: %v", seen, err)
			continue
		}
		if cfg.siteFilter != "" && row.Site != normalizeSiteLabel(cfg.siteFilter) {
			skipped++
			continue
		}

		if cfg.skipExisting {
			exists, err := operatorReportExists(context.Background(), reportStore.DB, row)
			if err != nil {
				failed++
				log.Printf("dedupe check failed for %s @ %s: %v", row.Site, row.CreatedAt.Format(time.RFC3339), err)
				continue
			}
			if exists {
				duplicates++
				if cfg.verbose {
					log.Printf("skip existing: site=%s created_at=%s title=%q", row.Site, row.CreatedAt.Format(time.RFC3339), row.Title)
				}
				continue
			}
		}

		if cfg.verbose {
			log.Printf("mapped: site=%s created_at=%s title=%q author=%q", row.Site, row.CreatedAt.Format(time.RFC3339), row.Title, nullableString(row.CreatedByEmail))
		}

		if cfg.dryRun {
			skipped++
			continue
		}
		if err := insertOperatorReportRow(context.Background(), reportStore, row); err != nil {
			failed++
			log.Printf("insert failed for %s @ %s: %v", row.Site, row.CreatedAt.Format(time.RFC3339), err)
			continue
		}
		imported++
	}
	if err := cur.Err(); err != nil {
		return fmt.Errorf("mongo cursor error: %w", err)
	}

	log.Printf("legacy adminMonitoring import complete: seen=%d imported=%d dryrun_skipped=%d duplicates=%d failed=%d dry_run=%v",
		seen, imported, skipped, duplicates, failed, cfg.dryRun)
	return nil
}

func openSQL(driver, dsn string) (*database.SQLXClient, error) {
	switch strings.ToLower(strings.TrimSpace(driver)) {
	case "postgres", "postgresql":
		return database.NewPostgresClient(dsn)
	case "sqlite", "sqlite3":
		return database.NewSQLiteClient(dsn)
	default:
		return nil, fmt.Errorf("unsupported sql driver: %q", driver)
	}
}

type operatorReportImportRow struct {
	Site           string
	Title          string
	Body           string
	Status         string
	Severity       *string
	TagsJSON       *string
	CreatedAt      time.Time
	UpdatedAt      time.Time
	CreatedByEmail *string
	CreatedByName  *string
	CreatedBySub   *string
}

func mapLegacyAdminMonitoringDoc(doc bson.M) (operatorReportImportRow, error) {
	site := normalizeSiteLabel(getString(doc, "depLocation"))
	if site == "" {
		site = "bluerock"
	}
	comments := strings.TrimSpace(getString(doc, "comments"))
	if comments == "" {
		comments = "(legacy report with empty comments)"
	}
	createdAt := parseLegacyReportTimestamp(doc)
	title := buildLegacyReportTitle(doc, createdAt)
	body := buildLegacyReportBody(doc, comments)
	tagsJSON, err := encodeTags([]string{"legacy-import", "adminMonitoring"})
	if err != nil {
		return operatorReportImportRow{}, err
	}

	return operatorReportImportRow{
		Site:           site,
		Title:          title,
		Body:           body,
		Status:         "open",
		TagsJSON:       &tagsJSON,
		CreatedAt:      createdAt.UTC(),
		UpdatedAt:      createdAt.UTC(),
		CreatedByEmail: ptrIfNonEmpty(getString(doc, "email")),
		CreatedByName:  ptrIfNonEmpty(getString(doc, "submittedBy")),
		CreatedBySub:   nil,
	}, nil
}

func buildLegacyReportTitle(doc bson.M, ts time.Time) string {
	if v := strings.TrimSpace(getString(doc, "title")); v != "" {
		return v
	}
	site := normalizeSiteLabel(getString(doc, "depLocation"))
	if site == "" {
		return "Legacy Admin Report"
	}
	return fmt.Sprintf("Legacy Admin Report (%s %s)", site, ts.UTC().Format("2006-01-02"))
}

func buildLegacyReportBody(doc bson.M, comments string) string {
	var b strings.Builder
	b.WriteString(comments)
	b.WriteString("\n\n")
	b.WriteString("[Legacy Import Metadata]\n")
	if id, ok := doc["_id"]; ok {
		b.WriteString("mongo_id: ")
		b.WriteString(fmt.Sprint(id))
		b.WriteString("\n")
	}
	if d := strings.TrimSpace(getString(doc, "date")); d != "" {
		b.WriteString("legacy_date: ")
		b.WriteString(d)
		b.WriteString("\n")
	}
	if t := strings.TrimSpace(getString(doc, "time")); t != "" {
		b.WriteString("legacy_time: ")
		b.WriteString(t)
		b.WriteString("\n")
	}
	return strings.TrimSpace(b.String())
}

func parseLegacyReportTimestamp(doc bson.M) time.Time {
	if v, ok := doc["timestamp"]; ok {
		switch t := v.(type) {
		case primitive.DateTime:
			return t.Time().UTC()
		case time.Time:
			return t.UTC()
		case string:
			if parsed, ok := parseTimestampString(t); ok {
				return parsed.UTC()
			}
		}
	}
	dateStr := strings.TrimSpace(getString(doc, "date"))
	timeStr := strings.TrimSpace(getString(doc, "time"))
	if dateStr != "" || timeStr != "" {
		if parsed, ok := parseLegacyDateTime(dateStr, timeStr); ok {
			return parsed.UTC()
		}
	}
	return time.Now().UTC()
}

func parseTimestampString(s string) (time.Time, bool) {
	for _, layout := range []string{
		time.RFC3339Nano,
		time.RFC3339,
		"2006-01-02 15:04:05",
		"1/2/2006 3:04 PM",
		"01/02/2006 03:04 PM",
	} {
		if t, err := time.Parse(layout, strings.TrimSpace(s)); err == nil {
			return t, true
		}
	}
	return time.Time{}, false
}

func parseLegacyDateTime(dateStr, timeStr string) (time.Time, bool) {
	loc, _ := time.LoadLocation("America/Los_Angeles")
	raw := strings.TrimSpace(strings.TrimSpace(dateStr) + " " + strings.TrimSpace(timeStr))
	for _, layout := range []string{
		"1/2/2006 3:04 PM",
		"01/02/2006 03:04 PM",
		"2006-01-02 15:04:05",
		"2006-01-02 15:04",
	} {
		if t, err := time.ParseInLocation(layout, raw, loc); err == nil {
			return t, true
		}
	}
	if t, ok := parseTimestampString(raw); ok {
		return t, true
	}
	return time.Time{}, false
}

func normalizeSiteLabel(s string) string {
	v := strings.ToLower(strings.TrimSpace(s))
	v = strings.ReplaceAll(v, " ", "")
	switch v {
	case "bluerock":
		return "bluerock"
	case "santateresa":
		return "santateresa"
	case "pryorfarm", "pryorfarms":
		return "pryorfarm"
	default:
		return v
	}
}

func prettyLegacySite(site string) string {
	switch normalizeSiteLabel(site) {
	case "bluerock":
		return "Bluerock"
	case "santateresa":
		return "SantaTeresa"
	case "pryorfarm":
		return "PryorFarm"
	default:
		return site
	}
}

func getString(doc bson.M, key string) string {
	v, ok := doc[key]
	if !ok || v == nil {
		return ""
	}
	switch t := v.(type) {
	case string:
		return t
	default:
		return fmt.Sprint(t)
	}
}

func ptrIfNonEmpty(s string) *string {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil
	}
	return &s
}

func encodeTags(tags []string) (string, error) {
	b, err := json.Marshal(tags)
	if err != nil {
		return "", fmt.Errorf("encode tags: %w", err)
	}
	return string(b), nil
}

func operatorReportExists(ctx context.Context, db *sqlx.DB, row operatorReportImportRow) (bool, error) {
	query := db.Rebind(`SELECT 1 FROM operator_reports WHERE site = ? AND created_at = ? AND body = ? LIMIT 1`)
	var one int
	err := db.GetContext(ctx, &one, query, row.Site, row.CreatedAt, row.Body)
	if err == sql.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

func insertOperatorReportRow(ctx context.Context, store *reports.Store, row operatorReportImportRow) error {
	args := map[string]any{
		"site":             row.Site,
		"title":            row.Title,
		"body":             row.Body,
		"status":           row.Status,
		"severity":         row.Severity,
		"tags":             row.TagsJSON,
		"created_at":       row.CreatedAt,
		"updated_at":       row.UpdatedAt,
		"created_by_email": row.CreatedByEmail,
		"created_by_name":  row.CreatedByName,
		"created_by_sub":   row.CreatedBySub,
	}
	q := `INSERT INTO operator_reports
		(site, title, body, status, severity, tags, created_at, updated_at, created_by_email, created_by_name, created_by_sub)
		VALUES (:site, :title, :body, :status, :severity, :tags, :created_at, :updated_at, :created_by_email, :created_by_name, :created_by_sub)`

	query, params, err := sqlx.Named(q, args)
	if err != nil {
		return err
	}
	query = store.DB.Rebind(query)
	_, err = store.DB.ExecContext(ctx, query, params...)
	return err
}

func nullableString(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

