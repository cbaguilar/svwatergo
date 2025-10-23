package bluerock

import (
	"time"
)

//systemmanager.go

type BluerockManager struct {
	Datastore Datastore
}

func (b *BluerockManager) GetLatestBluerock() BluerockState {
	var latest, _ = b.Datastore.GetLatest()
	return latest
}

func (b *BluerockManager) GetLatest() (any, error) {
	return b.GetLatestBluerock, nil
}

func (b *BluerockManager) SaveData(rawData []byte) error { //unmarshal rawData into raw

	state, err := FromRawData(rawData)
	if err != nil {
		return err
	}
	return b.Datastore.SaveState(state)
}

func (b *BluerockManager) GetRange(start time.Time, end time.Time) ([]any, error) {
	return b.Datastore.GetRange(start, end)
}

func (b *BluerockManager) ValidateState(state *BluerockState) error {
	return nil
}
