// Main entrypoint for new data coming into our system
package systemservice

import (
	"encoding/json"
	"fmt"
)

// Data ingestion type
type DataIngestionService struct {
	Managers map[string]SystemManager
}

func (s *DataIngestionService) Consume(rawData []byte) error {
	var record map[string]interface{}

	if err := json.Unmarshal(rawData, &record); err != nil {
		return fmt.Errorf("invalid json: %w", err)
	}

	locationRaw, ok := record["location"]
	if !ok {
		return fmt.Errorf("missing 'location' field")
	}

	location, ok := locationRaw.(string)
	if !ok {
		return fmt.Errorf("invalid 'location' field type")
	}

	manager, exists := s.Managers[location]
	if !exists {
		return fmt.Errorf("no manager found for location: %s", location)
	}

	return manager.SaveData(rawData)
}
