package santateresa

import (
	"fmt"
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
)

const (
	DefaultTableName = "santateresa_plc_data"
)

type SantaTeresaDatastore interface {
	SaveState(state *SantaTeresaState) error
	GetRange(start, end time.Time) ([]SantaTeresaState, error)
	GetLatest() (SantaTeresaState, error)
}

type SantaTeresaDBStore struct {
	Client    database.SQLXClient
	TableName string
}

func NewSantaTeresaDBStore(client database.SQLXClient) *SantaTeresaDBStore {
	return &SantaTeresaDBStore{Client: client, TableName: DefaultTableName}
}

func (s *SantaTeresaDBStore) SaveState(st *SantaTeresaState) error {
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

func (s *SantaTeresaDBStore) GetLatest() (SantaTeresaState, error) {
	q := fmt.Sprintf("SELECT * FROM %s ORDER BY recordtime DESC LIMIT 1", s.TableName)
	var out SantaTeresaState
	if err := s.Client.DB.Get(&out, q); err != nil {
		return SantaTeresaState{}, err
	}
	return out, nil
}

func (s *SantaTeresaDBStore) GetRange(start, end time.Time) ([]SantaTeresaState, error) {
	q := fmt.Sprintf(`SELECT * FROM %s WHERE recordtime BETWEEN ? AND ? ORDER BY recordtime ASC`, s.TableName)
	q = s.Client.DB.Rebind(q)
	var out []SantaTeresaState
	if err := s.Client.DB.Select(&out, q, start, end); err != nil {
		return nil, err
	}
	return out, nil
}
