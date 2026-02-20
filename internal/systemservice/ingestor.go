// Main entrypoint for new data coming into our system
package systemservice

import (
	"encoding/json"
	"fmt"
	"strings"
)

// Data ingestion type
type DataIngestionService struct {
	Reg      Registry
	OnIngest func(site string)
}

func (s *DataIngestionService) Consume(rawData []byte) error {
	var record map[string]any
	if err := json.Unmarshal(rawData, &record); err != nil {
		return fmt.Errorf("invalid json: %w", err)
	}
	v, ok := record["location"]
	if !ok {
		return fmt.Errorf("missing 'location' field")
	}
	loc, ok := v.(string)
	if !ok {
		return fmt.Errorf("invalid 'location' field type")
	}
	key := strings.ToLower(strings.TrimSpace(loc))

	mgr, exists := s.Reg.Get(key)
	if !exists {
		return fmt.Errorf("no manager found for location: %s", key)
	}
	if err := mgr.SaveData(rawData); err != nil {
		return err
	}
	if s.OnIngest != nil {
		s.OnIngest(key)
	}
	return nil
}
