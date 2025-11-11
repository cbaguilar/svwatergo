package pryorfarm

import (
	"encoding/json"
	"fmt"
	"log"
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/cbaguilar/svwatergo/internal/util"
)

// (same surface as BluerockManager so it plugs straight into DataIngestionService).

type PryorFarmManager struct {
	DB PryorFarmDatastore
}

func NewPryorFarmManager(client database.SQLXClient) *PryorFarmManager {
	log.Default().Println("Initializing PryorFarmManager with database client.")
	store := NewPryorFarmDBStore(client)
	if err := EnsureSchema(&client, store.TableName); err != nil {
		log.Printf("EnsureSchema(%s) error: %v", store.TableName, err)
	}
	return &PryorFarmManager{DB: store}
}

func (m *PryorFarmManager) GetLatestPryorFarm() PryorFarmState {
	latest, _ := m.DB.GetLatest()
	return latest
}

func (m *PryorFarmManager) GetLatest() (map[string]interface{}, error) {
	latest, err := m.DB.GetLatest()
	if err != nil {
		return nil, fmt.Errorf("failed to get latest PryorFarm state: %w", err)
	}
	return util.StructToMap(latest)
}
func (m *PryorFarmManager) SaveData(rawData []byte) error {
	state, err := FromRawData(rawData)
	log.Println("Saving PryorFarm state:", state)
	if err != nil {
		return err
	}
	return m.DB.SaveState(state)
}

func (m *PryorFarmManager) GetRange(start, end time.Time) ([]map[string]interface{}, error) {
	rows, err := m.DB.GetRange(start, end)
	if err != nil {
		return nil, err
	}
	out := make([]map[string]interface{}, 0, len(rows))
	for _, r := range rows {
		b, _ := json.Marshal(r)
		var m map[string]interface{}
		json.Unmarshal(b, &m)
		out = append(out, m)
	}
	return out, nil
}
