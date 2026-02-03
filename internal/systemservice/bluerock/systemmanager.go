package bluerock

import (
	"fmt"
	"log"
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/cbaguilar/svwatergo/internal/util"
)

//systemmanager.go

type BluerockManager struct {
	DB BluerockDatastore
}

func NewBluerockManager(client database.SQLXClient) *BluerockManager {
	log.Default().Println("Initializing BluerockManager with database client.")
	ourDbstore := NewBluerockDBStore(client)
	EnsureSchema(&client, ourDbstore.Store.TableName)
	return &BluerockManager{
		DB: ourDbstore,
	}
}

func (b *BluerockManager) GetLatestBluerock() BluerockState {
	var latest, _ = b.DB.GetLatest()
	return latest
}

func (b *BluerockManager) GetLatest() (map[string]interface{}, error) {
	latest, err := b.DB.GetLatest()
	if err != nil {
		return nil, fmt.Errorf("failed to get latest Bluerock state: %w", err)
	}
	m, err := util.StructToMap(latest)
	if err != nil {
		return nil, fmt.Errorf("StructToMap failed: %w", err)
	}
	return m, nil
}

func (b *BluerockManager) SaveData(rawData []byte) error { //unmarshal rawData into raw

	state, err := FromRawData(rawData)
	log.Println("Saving Bluerock state:", state)
	if err != nil {
		return err
	}
	return b.DB.SaveState(state)
}

func (b *BluerockManager) GetRange(start time.Time, end time.Time) ([]map[string]interface{}, error) {
	rows, err := b.DB.GetRange(start, end)
	if err != nil {
		return nil, err
	}
	return util.StructsToMaps(rows)
}

func (b *BluerockManager) Coverage() (systemservice.Coverage, error) {
	return b.DB.Coverage()
}

func (b *BluerockManager) ValidateState(state *BluerockState) error {
	return nil
}
