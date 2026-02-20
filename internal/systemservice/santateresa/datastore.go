package santateresa

import (
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/cbaguilar/svwatergo/internal/systemservice/schema"
)

const (
	DefaultTableName = "santa_teresa_plc_values"
)

type SantaTeresaDatastore interface {
	SaveState(state *SantaTeresaState) error
	GetRange(start, end time.Time) ([]SantaTeresaState, error)
	GetRangeSampled(start, end time.Time, sample string, maxPoints int) ([]SantaTeresaState, error)
	GetLatest() (SantaTeresaState, error)
	Coverage() (systemservice.Coverage, error)
}

type SantaTeresaDBStore struct {
	Store *systemservice.SQLStore
}

func NewSantaTeresaDBStore(client database.SQLXClient) *SantaTeresaDBStore {
	return &SantaTeresaDBStore{
		Store: systemservice.NewSQLStore(client, DefaultTableName, schema.InsertColumns(TableDef)),
	}
}

func (s *SantaTeresaDBStore) SaveState(st *SantaTeresaState) error {
	return s.Store.InsertNamed(st)
}

func (s *SantaTeresaDBStore) GetLatest() (SantaTeresaState, error) {
	var out SantaTeresaState
	if err := s.Store.GetLatest(&out); err != nil {
		return SantaTeresaState{}, err
	}
	return out, nil
}

func (s *SantaTeresaDBStore) GetRange(start, end time.Time) ([]SantaTeresaState, error) {
	var out []SantaTeresaState
	if err := s.Store.GetRange(&out, start, end); err != nil {
		return nil, err
	}
	return out, nil
}

func (s *SantaTeresaDBStore) GetRangeSampled(start, end time.Time, sample string, maxPoints int) ([]SantaTeresaState, error) {
	var out []SantaTeresaState
	if err := s.Store.GetRangeSampled(&out, start, end, sample, maxPoints); err != nil {
		return nil, err
	}
	return out, nil
}

func (s *SantaTeresaDBStore) Coverage() (systemservice.Coverage, error) {
	return s.Store.Coverage()
}
