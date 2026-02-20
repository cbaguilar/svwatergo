package systemservice

import (
	"fmt"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
)

type SQLStore struct {
	Client     database.SQLXClient
	TableName  string
	InsertCols []string
}

func NewSQLStore(client database.SQLXClient, table string, cols []string) *SQLStore {
	return &SQLStore{
		Client:     client,
		TableName:  table,
		InsertCols: cols,
	}
}

func (s *SQLStore) InsertNamed(state any) error {
	if len(s.InsertCols) == 0 {
		return fmt.Errorf("no insert columns for %s", s.TableName)
	}
	q := buildInsertQuery(s.TableName, s.InsertCols)
	_, err := s.Client.DB.NamedExec(q, state)
	return err
}

func (s *SQLStore) GetLatest(dest any) error {
	q := fmt.Sprintf("SELECT * FROM %s ORDER BY plctime DESC LIMIT 1", s.TableName)
	if s.Client.Driver == "sqlite3" {
		q = fmt.Sprintf("SELECT * FROM %s ORDER BY datetime(plctime) DESC LIMIT 1", s.TableName)
	}
	return s.Client.DB.Get(dest, q)
}

func (s *SQLStore) GetRange(dest any, start, end time.Time) error {
	if s.Client.Driver == "sqlite3" {
		q := fmt.Sprintf("SELECT * FROM %s WHERE datetime(plctime) BETWEEN datetime(?) AND datetime(?) ORDER BY datetime(plctime) ASC", s.TableName)
		return s.Client.DB.Select(dest, q, start.UTC().Format(time.RFC3339Nano), end.UTC().Format(time.RFC3339Nano))
	}
	q := fmt.Sprintf("SELECT * FROM %s WHERE plctime BETWEEN ? AND ? ORDER BY plctime ASC", s.TableName)
	q = s.Client.DB.Rebind(q)
	return s.Client.DB.Select(dest, q, start, end)
}

func (s *SQLStore) GetRangeSampled(dest any, start, end time.Time, sample string, maxPoints int) error {
	// For SQLite or disabled sampling, use the normal range path.
	if s.Client.Driver != "postgres" || sample == "none" || maxPoints <= 0 {
		return s.GetRange(dest, start, end)
	}

	switch sample {
	case "stride":
		// Push down downsampling into Postgres: split ordered rows into buckets and
		// pick the earliest row from each bucket.
		q := fmt.Sprintf(`
WITH filtered AS (
  SELECT * FROM %s
  WHERE plctime BETWEEN ? AND ?
),
bucketed AS (
  SELECT filtered.*, ntile(?) OVER (ORDER BY plctime) AS b
  FROM filtered
),
picked AS (
  SELECT * FROM (
    SELECT bucketed.*, row_number() OVER (PARTITION BY b ORDER BY plctime) AS rn
    FROM bucketed
  ) x
  WHERE rn = 1
)
SELECT * FROM picked
ORDER BY plctime ASC
`, s.TableName)
		q = s.Client.DB.Rebind(q)
		return s.Client.DB.Select(dest, q, start, end, maxPoints)
	default:
		return s.GetRange(dest, start, end)
	}
}

func (s *SQLStore) Coverage() (Coverage, error) {
	q := fmt.Sprintf(`
SELECT
  MIN(plctime) AS min_plctime,
  MAX(plctime) AS max_plctime,
  MAX(recordtime) AS max_recordtime,
  COUNT(*) AS count
FROM %s
`, s.TableName)
	var c Coverage
	if err := s.Client.DB.Get(&c, q); err != nil {
		return Coverage{}, err
	}
	return c, nil
}

func buildInsertQuery(table string, cols []string) string {
	names := strings.Join(cols, ", ")
	vals := make([]string, 0, len(cols))
	for _, c := range cols {
		vals = append(vals, ":"+c)
	}
	return fmt.Sprintf("INSERT INTO %s (%s) VALUES (%s)", table, names, strings.Join(vals, ", "))
}
