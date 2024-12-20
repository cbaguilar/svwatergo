package sensor

import (
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/cbaguilar/svwatergo/internal/sensor/datamodels"
)

// SensorService describes the service for handling sensor data.

type SystemManager struct {
	ParseAndNormalizeData(rawJson []byte) (datamodels.RemoteSystemState, error)
	StoreData(data datamodels.RemoteSystemState) error
	LoadDataAtTime(time time.Time) (datamodels.RemoteSystemState, error)
	LoadDataInRange(start time.Time, end time.Time) ([]datamodels.RemoteSystemState, error)
	LoadRecentData() (datamodels.RemoteSystemState, error)
}

type DataIngestionService struct {
	Managers map[string]SystemManager
}

func ExtractLocation(rawJson []byte) (string, error) {
	//extract the location field from the raw json
	var data map[string]interface{}
	if err := json.Unmarshal(rawJson, &data); err != nil {
		return "", fmt.Errorf("failed to parse JSON: %w", err)
	}

	location, ok := data["location"].(string)
	if !ok {
		return "", errors.New("location field not found")
	}
	return location, nil

}

func (di *DataIngestionService) HandleData(rawJson []byte) error {
	//extract the system name field from the raw json
	var systemName, err = ExtractLocation(rawJson)
	if err != nil {
		return fmt.Errorf("failed to extract location: %w", err)
	}

	manager, exists := di.Managers[systemName]
	if !exists {
		return fmt.Errorf("system manager for %s not found", systemName)
	}
	dataParsed, parseErr := manager.ParseAndNormalizeData(rawJson)
	if parseErr != nil {
		return fmt.Errorf("failed to parse data: %w", parseErr)
	}
	storeErr := manager.StoreData(dataParsed)
	if storeErr != nil {
		return fmt.Errorf("failed to store data: %w", storeErr)
	}
	return nil
}

// GetDataIngestionService creates a new DataIngestionService
// with maps of systrem locations to their respective managers

//default map of system locations to their respective managers

func GetDataIngestionService() *DataIngestionService {
	var managers = make(map[string]SystemManager)
	managers["pryorfarms"] = NewPryorFarmsManager()
}