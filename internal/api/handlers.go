package api

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"

	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/gin-gonic/gin"
)

//gin handler, SaveSensorDataHandler

// SaveSensorDataHandler is a gin handler that saves sensor data to the database.
// It needs to take in the body bytes, and pass it to the ingestion service.
// the ingestion service knows how to parse the different types of data.
func SaveSensorDataHandler(ingestionService *systemservice.DataIngestionService) gin.HandlerFunc {
	return func(c *gin.Context) {
		log.Println("Received request to save sensor data.")
		var records []map[string]interface{}
		if err := c.BindJSON(&records); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid JSON"})
			return
		}

		for _, rec := range records {
			rawBytes, err := json.Marshal(rec)
			if err != nil {
				log.Println("Failed to marshal record:", err)
				c.JSON(http.StatusBadRequest, gin.H{"error": "failed to masrhsall record"})
				continue
			}
			if err := ingestionService.Consume(rawBytes); err != nil {
				log.Println("Failed to consume:", err)
				c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to process record", "details": fmt.Sprintf("%v", err)})
				continue
			}
		}

		log.Println("Successfully processed all records.")
		fmt.Printf("Processed %d records successfully.\n", len(records))
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	}
}
