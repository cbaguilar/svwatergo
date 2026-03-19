package systemservice_test

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/cbaguilar/svwatergo/internal/api"
	"github.com/cbaguilar/svwatergo/internal/metadata"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
)

// fake system manager, recording past calls
type fakeMgr struct{ saved [][]byte }

func (f *fakeMgr) SaveData(rawData []byte) error {
	f.saved = append(f.saved, rawData)
	return nil
}
func (f *fakeMgr) GetRange(start, end time.Time) ([]map[string]interface{}, error) {
	// TODO: more rigorous implementation (if needed)
	return nil, nil
}

func (f *fakeMgr) GetLatest() (map[string]interface{}, error) {
	return map[string]interface{}{"recordtime": "2025-11-05T03:12:41Z"}, nil
}

func (f *fakeMgr) Coverage() (systemservice.Coverage, error) {
	return systemservice.Coverage{}, nil
}

/* Tests the common situation where the system sends an array
* of records, some of which may fail. The response should be
* a Multi-Status (207) with details on which records failed.
 */
func TestSaveSensorDataHandler_207(t *testing.T) {
	f := &fakeMgr{}
	reg := systemservice.NewRegistry(map[string]systemservice.SystemManager{"fakesite": f})
	ing := systemservice.DataIngestionService{Reg: reg}
	meta := &metadata.Store{Sites: map[string]*metadata.SiteConfig{}}
	r := api.SetupRouter(&ing, reg, meta, nil, nil, nil, nil, nil, nil, nil, false, false, nil)

	// Two records, second has unknown site, expect fail

	body := []map[string]any{
		{"location": "fakesite", "plctime": "PLC#2025-11-11T04:33:30Z", "inletflow": "100.5"},
		{"location": "unknownsite", "plctime": "PLC#2025-11-11T04:33:31Z", "inletflow": "200.5"},
	}

	raw, _ := json.Marshal(body)
	w := httptest.NewRecorder()
	req, _ := http.NewRequest("POST", "/uploadSensorDataNew", bytes.NewReader(raw))
	req.Header.Set("Content-Type", "application/json")
	r.ServeHTTP(w, req)

	if w.Code != http.StatusMultiStatus {
		t.Fatalf("expected status %d, got %d, body %s", http.StatusMultiStatus, w.Code, w.Body.String())
	}

	// first should have been saved, second should have failed

	if len(f.saved) != 1 {
		t.Fatalf("expected 1 saved record, got %d", len(f.saved))
	}
}

func TestSaveSensorDataHandler_InvalidJSON(t *testing.T) {
	reg := systemservice.NewRegistry(
		map[string]systemservice.SystemManager{},
	)
	ing := systemservice.DataIngestionService{Reg: reg}
	meta := &metadata.Store{Sites: map[string]*metadata.SiteConfig{}}
	r := api.SetupRouter(&ing, reg, meta, nil, nil, nil, nil, nil, nil, nil, false, false, nil)

	w := httptest.NewRecorder()
	req, _ := http.NewRequest("POST", "/uploadSensorDataNew", bytes.NewReader([]byte(`invalid json`)))
	req.Header.Set("Content-Type", "application/json")
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected status %d, got %d, body %s", http.StatusBadRequest, w.Code, w.Body.String())
	}
}
