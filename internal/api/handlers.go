package api

import (
	"net/http"

	"github.com/cbaguilar/svwatergo/internal/sensor"
	"github.com/gin-gonic/gin"
)

//gin handler, SaveSensorDataHandler

// SaveSensorDataHandler is a gin handler that saves sensor data to the database.
// It needs to take in the body bytes, and pass it to the ingestion service.
// the ingestion service knows how to parse the different types of data.

func SaveSensorDataHandler(c *gin.Context, DataIngestionService sensor.DataIngestionService) {
	// Read the body from the request
	body, err := c.GetRawData()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Save the data
	err = DataIngestionService.HandleData(body)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Data saved successfully"})
}
