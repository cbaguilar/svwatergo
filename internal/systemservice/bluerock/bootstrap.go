// internal/systemservice/bluerock/bootstrap.go
package bluerock

import (
	"fmt"
	"log"

	"github.com/cbaguilar/svwatergo/internal/database"
)

func EnsureSchema(c *database.SQLXClient, table string) error {
	log.Default().Printf("Ensuring schema for table %s using driver %s", table, c.Driver)
	switch c.Driver {
	case "sqlite3":
		_, err := c.DB.Exec(fmt.Sprintf(`
CREATE TABLE IF NOT EXISTS %s (
  id INTEGER PRIMARY KEY,
  location TEXT NOT NULL,
  totalroflow INTEGER,
  totalfeedflow INTEGER,
  totalrecycleflow INTEGER,
  totaldelflow INTEGER,
  dumpproduct INTEGER,
  wellpumprun INTEGER,
  wellpumpauto INTEGER,
  feedpumprun INTEGER,
  ropumprun INTEGER,
  deliveryrun INTEGER,
  deliveryauto INTEGER,
  inletrun INTEGER,
  concbypassrun INTEGER,
  proddiversionrun INTEGER,
  plctime TEXT NOT NULL,
  permeateflow INTEGER,
  deliveryflow INTEGER,
  feedflow REAL,
  concentrateflow REAL,
  recycleflow INTEGER,
  feedtanklevel REAL,
  dailypermflow REAL,
  alarm INTEGER,
  alarmword INTEGER,
  rostandby INTEGER,
  state INTEGER,
  lockout INTEGER,
  runflush INTEGER,
  warnword0 INTEGER,
  warnword1 INTEGER,
  totalhrs INTEGER,
  permtds REAL,
  feedtds REAL,
  permnitrate REAL,
  permtemp REAL,
  prodtanklevel REAL,
  prodtankdisable INTEGER,
  prodtankdepth REAL,
  feedtankdepth REAL,
  residualtankdepth REAL,
  inletpressure REAL,
  concentratepressure REAL,
  permeatepressure REAL,
  ropressure REAL,
  deliverypressure REAL,
  feedpressure REAL,
  recyclevalveposition INTEGER,
  ropressctrlvalveposition INTEGER,
  ropumpspeed INTEGER,
  powermeter INTEGER,
  flushduret INTEGER,
  producttds REAL,
  chlorinepumprun INTEGER,
  residtankvalverun INTEGER,
  residualtanklevel REAL,
  recordtime TEXT NOT NULL,
  flushrun INTEGER,
  UNIQUE (location, plctime)
);
CREATE INDEX IF NOT EXISTS idx_%[1]s_recordtime ON %[1]s(recordtime);
`, table))
		return err

	case "postgres":
		_, err := c.DB.Exec(fmt.Sprintf(`
CREATE TABLE IF NOT EXISTS %s (
  id BIGSERIAL PRIMARY KEY,
  location TEXT NOT NULL,
  totalroflow BIGINT,
  totalfeedflow BIGINT,
  totalrecycleflow BIGINT,
  totaldelflow BIGINT,
  dumpproduct BOOLEAN,
  wellpumprun BOOLEAN,
  wellpumpauto BOOLEAN,
  feedpumprun BOOLEAN,
  ropumprun BOOLEAN,
  deliveryrun BOOLEAN,
  deliveryauto BOOLEAN,
  inletrun BOOLEAN,
  concbypassrun BOOLEAN,
  proddiversionrun BOOLEAN,
  plctime TIMESTAMPTZ NOT NULL,
  permeateflow BIGINT,
  deliveryflow BIGINT,
  feedflow DOUBLE PRECISION,
  concentrateflow DOUBLE PRECISION,
  recycleflow BIGINT,
  feedtanklevel DOUBLE PRECISION,
  dailypermflow DOUBLE PRECISION,
  alarm BOOLEAN,
  alarmword BIGINT,
  rostandby BOOLEAN,
  state BIGINT,
  lockout BOOLEAN,
  runflush BOOLEAN,
  warnword0 BIGINT,
  warnword1 BIGINT,
  totalhrs BIGINT,
  permtds DOUBLE PRECISION,
  feedtds DOUBLE PRECISION,
  permnitrate DOUBLE PRECISION,
  permtemp DOUBLE PRECISION,
  prodtanklevel DOUBLE PRECISION,
  prodtankdisable BOOLEAN,
  prodtankdepth DOUBLE PRECISION,
  feedtankdepth DOUBLE PRECISION,
  residualtankdepth DOUBLE PRECISION,
  inletpressure DOUBLE PRECISION,
  concentratepressure DOUBLE PRECISION,
  permeatepressure DOUBLE PRECISION,
  ropressure DOUBLE PRECISION,
  deliverypressure DOUBLE PRECISION,
  feedpressure DOUBLE PRECISION,
  recyclevalveposition BIGINT,
  ropressctrlvalveposition BIGINT,
  ropumpspeed BIGINT,
  powermeter BIGINT,
  flushduret BIGINT,
  producttds DOUBLE PRECISION,
  chlorinepumprun BOOLEAN,
  residtankvalverun BOOLEAN,
  residualtanklevel DOUBLE PRECISION,
  recordtime TIMESTAMPTZ NOT NULL,
  flushrun BOOLEAN,
  UNIQUE (location, plctime)
);
CREATE INDEX IF NOT EXISTS idx_%[1]s_recordtime ON %[1]s(recordtime);
`, table))
		return err

	default:
		return fmt.Errorf("unknown driver %q", c.Driver)
	}
}
