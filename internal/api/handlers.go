package api

import (
	"net/http"

	"github.com/cbaguilar/svwatergo/internal/sensor"
	"github.com/gin-gonic/gin"
)

func SaveSensorDataHandler(service sensor.DataIngestionService) gin.HandlerFunc {
	return func(c *gin.Context) {
		if c.Request.Method != http.MethodPost {
			c.JSON(http.StatusMethodNotAllowed, gin.H{"error": "Invalid request method"})
			return
		}

		// Parse the request body
		if err := c.BindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		service.HandleData(req.Data)

		c.Status(http.StatusCreated)
	}
}

// Helper function to parse the media type from the Content-Type header
func parseMediaType(contentType string) string {
	for i := 1; i < len(contentType); i++ {
		if contentType[i] == ';' {
			return contentType[:i]
		}
	}
	return contentType
}

type UploadDataV1Request struct {
	// Define the fields for your request here
}

func UploadDataV1() gin.HandlerFunc {
	return func(c *gin.Context) {
		if c.Request.Method != http.MethodPost {
			c.JSON(http.StatusMethodNotAllowed, gin.H{"error": "Invalid request method"})
			return
		}

		contentType := parseMediaType(c.GetHeader("Content-Type"))

		if contentType == "application/zip" {
			// Unzip the data...
			// TODO: Unzip data
		}

		// Handle other content types if necessary
	}
}
