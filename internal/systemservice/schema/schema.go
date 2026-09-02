package schema

import (
	"fmt"
	"strings"
	"unicode"

	"github.com/cbaguilar/svwatergo/internal/database"
)

func ValidateIdentifier(name string) error {
	name = strings.TrimSpace(name)
	if name == "" {
		return fmt.Errorf("identifier is empty")
	}
	for i, r := range name {
		if i == 0 {
			if r != '_' && !unicode.IsLetter(r) {
				return fmt.Errorf("invalid identifier %q", name)
			}
			continue
		}
		if r != '_' && !unicode.IsLetter(r) && !unicode.IsDigit(r) {
			return fmt.Errorf("invalid identifier %q", name)
		}
	}
	return nil
}

func QuoteIdentifier(name string) (string, error) {
	if err := ValidateIdentifier(name); err != nil {
		return "", err
	}
	return `"` + name + `"`, nil
}

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
	quotedTable, err := QuoteIdentifier(table)
	if err != nil {
		return err
	}
	cols := make([]string, 0, len(def.Columns)+1)
	for _, col := range def.Columns {
		quotedCol, err := QuoteIdentifier(col.Name)
		if err != nil {
			return err
		}
		colType := col.SQLiteType
		if c.Driver == "postgres" {
			colType = col.PostgresType
		}
		if colType == "" {
			return fmt.Errorf("missing type for column %s", col.Name)
		}
		line := fmt.Sprintf("%s %s", quotedCol, colType)
		if col.NotNull {
			line += " NOT NULL"
		}
		cols = append(cols, line)
	}

	if len(def.Unique) > 0 {
		unique := make([]string, 0, len(def.Unique))
		for _, col := range def.Unique {
			quotedCol, err := QuoteIdentifier(col)
			if err != nil {
				return err
			}
			unique = append(unique, quotedCol)
		}
		cols = append(cols, fmt.Sprintf("UNIQUE (%s)", strings.Join(unique, ", ")))
	}

	createSQL := fmt.Sprintf(
		"CREATE TABLE IF NOT EXISTS %s (\n  %s\n);",
		quotedTable,
		strings.Join(cols, ",\n  "),
	)
	if _, err := c.DB.Exec(createSQL); err != nil {
		return err
	}

	indexName, err := QuoteIdentifier("idx_" + table + "_plctime")
	if err != nil {
		return err
	}
	plcTime, err := QuoteIdentifier("plctime")
	if err != nil {
		return err
	}
	indexSQL := fmt.Sprintf("CREATE INDEX IF NOT EXISTS %s ON %s(%s);", indexName, quotedTable, plcTime)
	_, err = c.DB.Exec(indexSQL)
	return err
}
