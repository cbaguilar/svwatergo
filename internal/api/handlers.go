package api

import (
	"encoding/json"
	"log"
	"net/http"

	systemservice "github.com/cbaguilar/svwatergo/internal/system_service"
	"github.com/gin-gonic/gin"
)

//gin handler, SaveSensorDataHandler

// SaveSensorDataHandler is a gin handler that saves sensor data to the database.
// It needs to take in the body bytes, and pass it to the ingestion service.
// the ingestion service knows how to parse the different types of data.
func SaveSensorDataHandler(ingestionService *systemservice.DataIngestionService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var records []map[string]interface{}
		if err := c.BindJSON(&records); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid JSON"})
			return
		}

		for _, rec := range records {
			rawBytes, _ := json.Marshal(rec) // safe since you just parsed it
			if err := ingestionService.Consume(rawBytes); err != nil {
				log.Println("Failed to consume:", err)
				continue
			}
		}

		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	}
}
