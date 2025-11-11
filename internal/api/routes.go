package api

import (
	"net/http"

	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/gin-gonic/gin"
)

func SetupRouter(ingestion *systemservice.DataIngestionService, reg systemservice.Registry) *gin.Engine {
	// Disable Console Color
	// gin.DisableConsoleColor()
	r := gin.Default()

	// Ping test
	r.GET("/ping", func(c *gin.Context) {
		c.String(http.StatusOK, "pong")
	})

	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "healthy"})
	})

	state := NewStateAPI(reg)

	v1 := r.Group("/api/v1")
	{
		sites := v1.Group("/sites/:site")
		sites.GET("/state/latest", state.GetLatest)
		sites.GET("/state", state.GetRange) // ?start=&end=&fields=&sample=&max_points=&smooth=&window=
	}

	/// This is the v0 route, which we will re-implement for backwards compatibility
	// with the old Javascript server.
	r.POST("/UploadDataNew", SaveSensorDataHandler(ingestion))
	r.POST("/uploadSensorDataNew", SaveSensorDataHandler(ingestion)) // alias

	return r
}
