// Main entrypoint for new data coming into our system
package systemservice

import (
	"github.com/cbaguilar/svwatergo/internal/system_contract"
)

// Data ingestion type
type DataIngestionService struct {
	Managers map[string]system_contract.SystemManager
}
