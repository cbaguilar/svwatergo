package pryorfarm

import (
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/cbaguilar/svwatergo/internal/systemservice/schema"
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
	Store *systemservice.SQLStore
}

func NewPryorFarmDBStore(client database.SQLXClient) *PryorFarmDBStore {
	return &PryorFarmDBStore{
		Store: systemservice.NewSQLStore(client, DefaultTableName, schema.InsertColumns(TableDef)),
	}
}

func (s *PryorFarmDBStore) SaveState(st *PryorFarmState) error {
	return s.Store.InsertNamed(st)
}

func (s *PryorFarmDBStore) GetLatest() (PryorFarmState, error) {
	var out PryorFarmState
	if err := s.Store.GetLatest(&out); err != nil {
		return PryorFarmState{}, err
	}
	return out, nil
}

func (s *PryorFarmDBStore) GetRange(start, end time.Time) ([]PryorFarmState, error) {
	var out []PryorFarmState
	if err := s.Store.GetRange(&out, start, end); err != nil {
		return nil, err
	}
	return out, nil
}

func (s *PryorFarmDBStore) Coverage() (systemservice.Coverage, error) {
	return s.Store.Coverage()
}
