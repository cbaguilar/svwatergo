package bluerock

import (
	"time"

	// Import the new generic database package
	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/cbaguilar/svwatergo/internal/systemservice/schema"
)

const (
	DefaultTableName = "bluerock_plc_data"
)

type BluerockDatastore interface {
	SaveState(state *BluerockState) error
	// GetRange now returns the concrete type, making the manager's job easier
	GetRange(start, end time.Time) ([]BluerockState, error)
	GetLatest() (BluerockState, error)
	Coverage() (systemservice.Coverage, error)
}

type BluerockDBStore struct {
	Store *systemservice.SQLStore
}

func NewBluerockDBStore(client database.SQLXClient) *BluerockDBStore {
	return &BluerockDBStore{
		Store: systemservice.NewSQLStore(client, DefaultTableName, schema.InsertColumns(TableDef)),
	}
}

func (b *BluerockDBStore) SaveState(state *BluerockState) error {
	return b.Store.InsertNamed(state)
}

func (b *BluerockDBStore) GetLatest() (BluerockState, error) {
	var s BluerockState
	if err := b.Store.GetLatest(&s); err != nil {
		return BluerockState{}, err
	}
	return s, nil
}

func (b *BluerockDBStore) GetRange(start, end time.Time) ([]BluerockState, error) {
	var out []BluerockState
	if err := b.Store.GetRange(&out, start, end); err != nil {
		return nil, err
	}
	return out, nil
}

func (b *BluerockDBStore) Coverage() (systemservice.Coverage, error) {
	return b.Store.Coverage()
}
