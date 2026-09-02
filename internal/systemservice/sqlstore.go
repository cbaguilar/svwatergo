package systemservice

import (
	"fmt"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/cbaguilar/svwatergo/internal/systemservice/schema"
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
	q, err := buildInsertQuery(s.TableName, s.InsertCols)
	if err != nil {
		return err
	}
	_, err = s.Client.DB.NamedExec(q, state)
	return err
}

func (s *SQLStore) GetLatest(dest any) error {
	table, err := schema.QuoteIdentifier(s.TableName)
	if err != nil {
		return err
	}
	q := fmt.Sprintf("SELECT * FROM %s ORDER BY plctime DESC LIMIT 1", table)
	if s.Client.Driver == "sqlite3" {
		q = fmt.Sprintf("SELECT * FROM %s ORDER BY datetime(plctime) DESC LIMIT 1", table)
	}
	return s.Client.DB.Get(dest, q)
}

func (s *SQLStore) GetRange(dest any, start, end time.Time) error {
	table, err := schema.QuoteIdentifier(s.TableName)
	if err != nil {
		return err
	}
	if s.Client.Driver == "sqlite3" {
		q := fmt.Sprintf("SELECT * FROM %s WHERE datetime(plctime) BETWEEN datetime(?) AND datetime(?) ORDER BY datetime(plctime) ASC", table)
		return s.Client.DB.Select(dest, q, start.UTC().Format(time.RFC3339Nano), end.UTC().Format(time.RFC3339Nano))
	}
	q := fmt.Sprintf("SELECT * FROM %s WHERE plctime BETWEEN ? AND ? ORDER BY plctime ASC", table)
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
		table, err := schema.QuoteIdentifier(s.TableName)
		if err != nil {
			return err
		}
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
`, table)
		q = s.Client.DB.Rebind(q)
		return s.Client.DB.Select(dest, q, start, end, maxPoints)
	default:
		return s.GetRange(dest, start, end)
	}
}

func (s *SQLStore) Coverage() (Coverage, error) {
	table, err := schema.QuoteIdentifier(s.TableName)
	if err != nil {
		return Coverage{}, err
	}
	q := fmt.Sprintf(`
SELECT
  MIN(plctime) AS min_plctime,
  MAX(plctime) AS max_plctime,
  MAX(recordtime) AS max_recordtime,
  COUNT(*) AS count
FROM %s
`, table)
	var c Coverage
	if err := s.Client.DB.Get(&c, q); err != nil {
		return Coverage{}, err
	}
	return c, nil
}

func buildInsertQuery(table string, cols []string) (string, error) {
	quotedTable, err := schema.QuoteIdentifier(table)
	if err != nil {
		return "", err
	}
	names := make([]string, 0, len(cols))
	vals := make([]string, 0, len(cols))
	for _, c := range cols {
		quotedCol, err := schema.QuoteIdentifier(c)
		if err != nil {
			return "", err
		}
		names = append(names, quotedCol)
		vals = append(vals, ":"+c)
	}
	return fmt.Sprintf("INSERT INTO %s (%s) VALUES (%s)", quotedTable, strings.Join(names, ", "), strings.Join(vals, ", ")), nil
}
