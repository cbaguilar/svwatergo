package api

import (
	"encoding/json"
	"net/http"

	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/gin-gonic/gin"
)

//gin handler, SaveSensorDataHandler

// SaveSensorDataHandler is a gin handler that saves sensor data to the database.
// It needs to take in the body bytes, and pass it to the ingestion service.

func SaveSensorDataHandler(ingestion *systemservice.DataIngestionService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var records []map[string]any
		if err := c.BindJSON(&records); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid JSON"})
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
