package bluerock

import (
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
)

//systemmanager.go

type BluerockManager struct {
	DB BluerockDatastore
}

func NewBluerockManager(client database.SQLXClient) *BluerockManager {
	ourDbstore := NewBluerockDBStore(client)
	return &BluerockManager{
		DB: ourDbstore,
	}
}

func (b *BluerockManager) GetLatestBluerock() BluerockState {
	var latest, _ = b.DB.GetLatest()
	return latest
}

func (b *BluerockManager) GetLatest() (map[string]interface{}, error) {
	return nil, nil
}

func (b *BluerockManager) SaveData(rawData []byte) error { //unmarshal rawData into raw

	state, err := FromRawData(rawData)
	if err != nil {
		return err
	}
	return b.DB.SaveState(state)
}

func (b *BluerockManager) GetRange(start time.Time, end time.Time) ([]map[string]interface{}, error) {
	return nil, nil
}

func (b *BluerockManager) ValidateState(state *BluerockState) error {
	return nil
}
