package database

import (
	"time"
)

type Datastore interface {
	SaveState(manager SystemManager, state SystemState) error
	GetRange(start, end time.Time) ([]any, error)
	GetLatest() (SystemState, error)
}
