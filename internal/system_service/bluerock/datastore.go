package bluerock

import (
	"fmt"
	"time"

	// Import the new generic database package
	"github.com/cbaguilar/svwatergo/internal/database"
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

func NewBluerockDBStore(client database.SQLXClient, tableName string) *BluerockDBStore {
	return &BluerockDBStore{
		Client:    client,
		TableName: tableName,
	}
}

func (b *BluerockDBStore) SaveState(state *BluerockState) error {
	// Minimal example; expand columns as needed (you can also use NamedExec)
	const q = `
		INSERT INTO %s (location, totalroflow, plctime, recordtime)
		VALUES ($1, $2, $3, $4)
	`
	_, err := b.Client.DB.Exec(fmt.Sprintf(q, b.TableName),
		state.Location, state.TotalROFlow, state.PLCTime, state.RecordTime)
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
	q := fmt.Sprintf(`
		SELECT * FROM %s
		WHERE recordtime BETWEEN $1 AND $2
		ORDER BY recordtime ASC
	`, b.TableName)
	var out []BluerockState
	if err := b.Client.DB.Select(&out, q, start, end); err != nil {
		return nil, err
	}
	return out, nil
}
