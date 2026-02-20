package santateresa

import (
	"fmt"
	"log"
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/cbaguilar/svwatergo/internal/util"
)

// (same surface as BluerockManager so it plugs straight into DataIngestionService).

type SantaTeresaManager struct {
	DB SantaTeresaDatastore
}

func NewSantaTeresaManager(client database.SQLXClient) *SantaTeresaManager {
	log.Default().Println("Initializing SantaTeresaManager with database client.")
	store := NewSantaTeresaDBStore(client)
	if err := EnsureSchema(&client, store.Store.TableName); err != nil {
		log.Printf("EnsureSchema(%s) error: %v", store.Store.TableName, err)
	}
	return &SantaTeresaManager{DB: store}
}

func (m *SantaTeresaManager) GetLatestSantaTeresa() SantaTeresaState {
	latest, _ := m.DB.GetLatest()
	return latest
}

func (m *SantaTeresaManager) GetLatest() (map[string]interface{}, error) {
	latest, err := m.DB.GetLatest()
	if err != nil {
		return nil, fmt.Errorf("failed to get latest SantaTeresa state: %w", err)
	}
	return util.StructToMap(latest)
}

func (m *SantaTeresaManager) SaveData(rawData []byte) error {
	state, err := FromRawData(rawData)
	log.Println("Saving SantaTeresa state:", state)
	if err != nil {
		return err
	}
	return m.DB.SaveState(state)
}

func (m *SantaTeresaManager) GetRange(start, end time.Time) ([]map[string]interface{}, error) {
	rows, err := m.DB.GetRange(start, end)
	if err != nil {
		return nil, err
	}
	return util.StructsToMaps(rows)
}

func (m *SantaTeresaManager) GetRangeSampled(start, end time.Time, sample string, maxPoints int) ([]map[string]interface{}, error) {
	rows, err := m.DB.GetRangeSampled(start, end, sample, maxPoints)
	if err != nil {
		return nil, err
	}
	return util.StructsToMaps(rows)
}

func (m *SantaTeresaManager) Coverage() (systemservice.Coverage, error) {
	return m.DB.Coverage()
}
