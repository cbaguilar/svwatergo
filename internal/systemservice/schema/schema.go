package schema

import (
	"fmt"
	"strings"

	"github.com/cbaguilar/svwatergo/internal/database"
)

type ColumnDef struct {
	Name         string
	SQLiteType   string
	PostgresType string
	NotNull      bool
}

type TableDef struct {
	Columns []ColumnDef
	Unique  []string
}

func InsertColumns(def TableDef) []string {
	out := make([]string, 0, len(def.Columns))
	for _, c := range def.Columns {
		if strings.EqualFold(c.Name, "id") {
			continue
		}
		out = append(out, c.Name)
	}
	return out
}

func EnsureTable(c *database.SQLXClient, table string, def TableDef) error {
	cols := make([]string, 0, len(def.Columns)+1)
	for _, col := range def.Columns {
		colType := col.SQLiteType
		if c.Driver == "postgres" {
			colType = col.PostgresType
		}
		if colType == "" {
			return fmt.Errorf("missing type for column %s", col.Name)
		}
		line := fmt.Sprintf("%s %s", col.Name, colType)
		if col.NotNull {
			line += " NOT NULL"
		}
		cols = append(cols, line)
	}

	if len(def.Unique) > 0 {
		cols = append(cols, fmt.Sprintf("UNIQUE (%s)", strings.Join(def.Unique, ", ")))
	}

	createSQL := fmt.Sprintf(
		"CREATE TABLE IF NOT EXISTS %s (\n  %s\n);",
		table,
		strings.Join(cols, ",\n  "),
	)
	if _, err := c.DB.Exec(createSQL); err != nil {
		return err
	}

	indexSQL := fmt.Sprintf("CREATE INDEX IF NOT EXISTS idx_%s_plctime ON %s(plctime);", table, table)
	_, err := c.DB.Exec(indexSQL)
	return err
}
