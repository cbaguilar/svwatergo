package pryorfarm

import (
	"log"

	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/cbaguilar/svwatergo/internal/systemservice/schema"
)

func EnsureSchema(c *database.SQLXClient, table string) error {
	log.Default().Printf("Ensuring schema for table %s using driver %s", table, c.Driver)
	return schema.EnsureTable(c, table, TableDef)
}
