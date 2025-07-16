package system_contract

import (
	"time"
)

type Datastore interface {
	SaveState(state SystemState) error
	GetRange(start, end time.Time) ([]SystemState, error)
}
