package database

import (
	"time"

	"github.com/cbaguilar/svwatergo/internal/systemservice"
)

type Datastore interface {
	SaveState(state systemservice.SystemState) error
	GetRange(start, end time.Time) ([]any, error)
	GetLatest() (systemservice.SystemState, error)
}
