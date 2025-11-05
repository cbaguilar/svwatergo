package bluerock

import (
	"fmt"
	"time"

	// Import the new generic database package
	"github.com/cbaguilar/svwatergo/internal/database"
)

const (
	DefaultTableName = "bluerock_plc_data"
)

type BluerockDatastore interface {
	SaveState(state *BluerockState) error
	// GetRange now returns the concrete type, making the manager's job easier
	GetRange(start, end time.Time) ([]BluerockState, error)
	GetLatest() (BluerockState, error)
}

type BluerockDBStore struct {
	Client    database.SQLXClient
	TableName string
}

func NewBluerockDBStore(client database.SQLXClient) *BluerockDBStore {
	return &BluerockDBStore{
		Client:    client,
		TableName: DefaultTableName,
	}
}

func (b *BluerockDBStore) SaveState(state *BluerockState) error {
	q := fmt.Sprintf(`
INSERT INTO %s (
  location, totalroflow, totalfeedflow, totalrecycleflow, totaldelflow,
  dumpproduct, wellpumprun, wellpumpauto, feedpumprun, ropumprun,
  deliveryrun, deliveryauto, inletrun, concbypassrun, proddiversionrun,
  plctime, permeateflow, deliveryflow, feedflow, concentrateflow,
  recycleflow, feedtanklevel, dailypermflow, alarm, alarmword,
  rostandby, state, lockout, runflush, warnword0, warnword1, totalhrs,
  permtds, feedtds, permnitrate, permtemp, prodtanklevel, prodtankdisable,
  prodtankdepth, feedtankdepth, residualtankdepth, inletpressure,
  concentratepressure, permeatepressure, ropressure, deliverypressure,
  feedpressure, recyclevalveposition, ropressctrlvalveposition,
  ropumpspeed, powermeter, flushduret, producttds, chlorinepumprun,
  residtankvalverun, residualtanklevel, recordtime, flushrun
)
VALUES (
  :location, :totalroflow, :totalfeedflow, :totalrecycleflow, :totaldelflow,
  :dumpproduct, :wellpumprun, :wellpumpauto, :feedpumprun, :ropumprun,
  :deliveryrun, :deliveryauto, :inletrun, :concbypassrun, :proddiversionrun,
  :plctime, :permeateflow, :deliveryflow, :feedflow, :concentrateflow,
  :recycleflow, :feedtanklevel, :dailypermflow, :alarm, :alarmword,
  :rostandby, :state, :lockout, :runflush, :warnword0, :warnword1, :totalhrs,
  :permtds, :feedtds, :permnitrate, :permtemp, :prodtanklevel, :prodtankdisable,
  :prodtankdepth, :feedtankdepth, :residualtankdepth, :inletpressure,
  :concentratepressure, :permeatepressure, :ropressure, :deliverypressure,
  :feedpressure, :recyclevalveposition, :ropressctrlvalveposition,
  :ropumpspeed, :powermeter, :flushduret, :producttds, :chlorinepumprun,
  :residtankvalverun, :residualtanklevel, :recordtime, :flushrun
)
`, b.TableName)

	_, err := b.Client.DB.NamedExec(q, state)
	return err
}

func (b *BluerockDBStore) GetLatest() (BluerockState, error) {
	q := fmt.Sprintf("SELECT * FROM %s ORDER BY recordtime DESC LIMIT 1", b.TableName)
	var s BluerockState
	if err := b.Client.DB.Get(&s, q); err != nil {
		return BluerockState{}, err
	}
	return s, nil
}

func (b *BluerockDBStore) GetRange(start, end time.Time) ([]BluerockState, error) {
	q := fmt.Sprintf(`SELECT * FROM %s WHERE recordtime BETWEEN ? AND ? ORDER BY recordtime ASC`, b.TableName)
	q = b.Client.DB.Rebind(q)
	var out []BluerockState
	if err := b.Client.DB.Select(&out, q, start, end); err != nil {
		return nil, err
	}
	return out, nil
}
