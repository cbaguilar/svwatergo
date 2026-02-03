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
	return s.Client.DB.Get(dest, q)
}

func (s *SQLStore) GetRange(dest any, start, end time.Time) error {
	q := fmt.Sprintf("SELECT * FROM %s WHERE plctime BETWEEN ? AND ? ORDER BY plctime ASC", s.TableName)
	q = s.Client.DB.Rebind(q)
	return s.Client.DB.Select(dest, q, start, end)
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
