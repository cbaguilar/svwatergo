package api

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"

	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/gin-gonic/gin"
)

//gin handler, SaveSensorDataHandler

// SaveSensorDataHandler is a gin handler that saves sensor data to the database.
// It needs to take in the body bytes, and pass it to the ingestion service.

func SaveSensorDataHandler(ingestion *systemservice.DataIngestionService) gin.HandlerFunc {
	return func(c *gin.Context) {
		records, err := parseUploadRecords(c)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		type recResult struct {
			Index  int         `json:"index"`
			Status string      `json:"status"`
			Error  string      `json:"error,omitempty"`
			Detail interface{} `json:"detail,omitempty"`
		}
		results := make([]recResult, 0, len(records))

		for i, rec := range records {
			raw, err := json.Marshal(rec)
			if err != nil {
				results = append(results, recResult{
					Index:  i,
					Status: "failed",
					Error:  "marshal record",
				})
				continue
			}
			if err := ingestion.Consume(raw); err != nil {
				results = append(results, recResult{
					Index:  i,
					Status: "failed",
					Error:  err.Error(),
				})
				continue
			}
			results = append(results, recResult{
				Index:  i,
				Status: "ok",
			})
		}

		code := http.StatusOK
		for _, r := range results {
			if r.Status != "ok" {
				code = http.StatusMultiStatus /* 207 */
				break
			}
		}
		c.JSON(code, gin.H{"results": results})
	}
}

func parseUploadRecords(c *gin.Context) ([]map[string]any, error) {
	ct := c.GetHeader("Content-Type")
	if strings.Contains(strings.ToLower(ct), "application/zip") {
		return parseZipRecords(c.Request.Body)
	}

	body, err := io.ReadAll(c.Request.Body)
	if err != nil {
		return nil, errors.New("failed to read body")
	}
	return parseJSONRecords(body)
}

func parseJSONRecords(body []byte) ([]map[string]any, error) {
	var records []map[string]any
	if err := json.Unmarshal(body, &records); err == nil {
		return records, nil
	}
	var single map[string]any
	if err := json.Unmarshal(body, &single); err == nil {
		return []map[string]any{single}, nil
	}
	return nil, errors.New("invalid JSON")
}

func parseZipRecords(r io.Reader) ([]map[string]any, error) {
	raw, err := io.ReadAll(r)
	if err != nil {
		return nil, errors.New("failed to read zip body")
	}
	zr, err := zip.NewReader(bytes.NewReader(raw), int64(len(raw)))
	if err != nil {
		return nil, errors.New("invalid zip")
	}
	for _, f := range zr.File {
		name := strings.ToLower(f.Name)
		if name == "temp.txt" || strings.HasSuffix(name, "/temp.txt") {
			rc, err := f.Open()
			if err != nil {
				return nil, errors.New("failed to open temp.txt")
			}
			defer rc.Close()
			body, err := io.ReadAll(rc)
			if err != nil {
				return nil, errors.New("failed to read temp.txt")
			}
			return parseJSONRecords(body)
		}
	}
	return nil, errors.New("temp.txt not found in zip")
}
