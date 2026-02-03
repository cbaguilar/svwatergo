package pryorfarm

import (
	"fmt"
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
)

const (
	DefaultTableName = "pryorfarm_plc_data"
)

type PryorFarmDatastore interface {
	SaveState(state *PryorFarmState) error
	GetRange(start, end time.Time) ([]PryorFarmState, error)
	GetLatest() (PryorFarmState, error)
	Coverage() (systemservice.Coverage, error)
}

type PryorFarmDBStore struct {
	Client    database.SQLXClient
	TableName string
}

func NewPryorFarmDBStore(client database.SQLXClient) *PryorFarmDBStore {
	return &PryorFarmDBStore{Client: client, TableName: DefaultTableName}
}

func (s *PryorFarmDBStore) SaveState(st *PryorFarmState) error {
	q := fmt.Sprintf(`
INSERT INTO %s (
  location, totalroflow, totalinletflow, totalconcflow, totaldelflow,
  dumpproduct, wellpumprun, wellpumpauto, feedpumprun, ropumprun,
  deliveryrun, deliveryauto, inletrun, flushrun, concbypassrun,
  proddiversionrun, flushdiversionrun, plctime, permeateflow, deliveryflow,
  inletflow, concentrateflow, recycleflow, feedtanklevel, dailypermflow,
  dailyinletflow, alarm, alarmword, rostandby, state, lockout, runflush,
  warnword0, warnword1, totalhrs, permtds, feedtds, permnitrate, permtemp,
  prodtanklevel, prodtankdisable, prodtankdepth, feedtankdepth, flushtanklevel,
  flushtankdepth, flushtankfull, inletpressure, concentratepressure,
  permeatepressure, ropressure, deliverypressure, feedpressure,
  recyclevalveposition, ropressctrlvalveposition, ropumpspeed, powermeter,
  flushduret, producttds, recordtime
) VALUES (
  :location, :totalroflow, :totalinletflow, :totalconcflow, :totaldelflow,
  :dumpproduct, :wellpumprun, :wellpumpauto, :feedpumprun, :ropumprun,
  :deliveryrun, :deliveryauto, :inletrun, :flushrun, :concbypassrun,
  :proddiversionrun, :flushdiversionrun, :plctime, :permeateflow, :deliveryflow,
  :inletflow, :concentrateflow, :recycleflow, :feedtanklevel, :dailypermflow,
  :dailyinletflow, :alarm, :alarmword, :rostandby, :state, :lockout, :runflush,
  :warnword0, :warnword1, :totalhrs, :permtds, :feedtds, :permnitrate, :permtemp,
  :prodtanklevel, :prodtankdisable, :prodtankdepth, :feedtankdepth, :flushtanklevel,
  :flushtankdepth, :flushtankfull, :inletpressure, :concentratepressure,
  :permeatepressure, :ropressure, :deliverypressure, :feedpressure,
  :recyclevalveposition, :ropressctrlvalveposition, :ropumpspeed, :powermeter,
  :flushduret, :producttds, :recordtime
)`, s.TableName)

	_, err := s.Client.DB.NamedExec(q, st)
	return err
}

func (s *PryorFarmDBStore) GetLatest() (PryorFarmState, error) {
	q := fmt.Sprintf("SELECT * FROM %s ORDER BY recordtime DESC LIMIT 1", s.TableName)
	var out PryorFarmState
	if err := s.Client.DB.Get(&out, q); err != nil {
		return PryorFarmState{}, err
	}
	return out, nil
}

func (s *PryorFarmDBStore) GetRange(start, end time.Time) ([]PryorFarmState, error) {
	q := fmt.Sprintf(`SELECT * FROM %s WHERE recordtime BETWEEN ? AND ? ORDER BY recordtime ASC`, s.TableName)
	q = s.Client.DB.Rebind(q)
	var out []PryorFarmState
	if err := s.Client.DB.Select(&out, q, start, end); err != nil {
		return nil, err
	}
	return out, nil
}

func (s *PryorFarmDBStore) Coverage() (systemservice.Coverage, error) {
	q := fmt.Sprintf(`
SELECT
  MIN(plctime) AS min_plctime,
  MAX(plctime) AS max_plctime,
  MAX(recordtime) AS max_recordtime,
  COUNT(*) AS count
FROM %s
`, s.TableName)
	var c systemservice.Coverage
	if err := s.Client.DB.Get(&c, q); err != nil {
		return systemservice.Coverage{}, err
	}
	return c, nil
}
