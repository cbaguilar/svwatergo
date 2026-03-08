package api_test

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/cbaguilar/svwatergo/internal/api"
	"github.com/cbaguilar/svwatergo/internal/metadata"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
)

type mgrLatest struct {
	data map[string]any
}

func (m mgrLatest) SaveData(rawData []byte) error {
	return nil
}

func (m mgrLatest) GetRange(_, _ time.Time) ([]map[string]interface{}, error) {
	return nil, nil
}

func (m mgrLatest) GetLatest() (map[string]interface{}, error) {
	return m.data, nil
}

func (m mgrLatest) Coverage() (systemservice.Coverage, error) {
	return systemservice.Coverage{}, nil
}

// Tests that we properly fail for an unknown location
func TestLatest_NotFound(t *testing.T) {
	m := mgrLatest{
		data: map[string]any{"recordtime": "2024-06-10T12:00:00Z", "a": "1"}}
	reg := systemservice.NewRegistry(map[string]systemservice.SystemManager{
		"testlocation": m,
	})

	meta := &metadata.Store{Sites: map[string]*metadata.SiteConfig{}}
	r := api.SetupRouter(&systemservice.DataIngestionService{Reg: reg}, reg, meta, nil, nil, nil, nil, nil, nil, false, false, nil)

	rr := httptest.NewRecorder()
	req, _ := http.NewRequest("GET", "/api/v1/sites/unknownloc/state/latest", nil)
	r.ServeHTTP(rr, req)

	if rr.Code != http.StatusNotFound {
		t.Fatalf("expected status %d, got %d, body %s", http.StatusNotFound, rr.Code, rr.Body.String())
	}
}

// Test happy path for getting latest state
func TestLatest_Success(t *testing.T) {
	m := mgrLatest{
		data: map[string]any{"recordtime": "2024-06-10T12:00:00Z", "a": "1"}}
	reg := systemservice.NewRegistry(map[string]systemservice.SystemManager{
		"testlocation": m,
	})

	meta := &metadata.Store{Sites: map[string]*metadata.SiteConfig{}}
	r := api.SetupRouter(&systemservice.DataIngestionService{Reg: reg}, reg, meta, nil, nil, nil, nil, nil, nil, false, false, nil)
	rr := httptest.NewRecorder()
	req, _ := http.NewRequest("GET", "/api/v1/sites/testlocation/state/latest", nil)
	r.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d, body %s", http.StatusOK, rr.Code, rr.Body.String())
	}
}
