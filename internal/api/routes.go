package api

import (
	"net/http"

	"github.com/cbaguilar/svwatergo/internal/sensor"
	"github.com/gin-gonic/gin"
)

func SetupRouter(sensorService sensor.DataIngestionService) *gin.Engine {
	// Disable Console Color
	// gin.DisableConsoleColor()
	r := gin.Default()

	// Ping test
	r.GET("/ping", func(c *gin.Context) {
		c.String(http.StatusOK, "pong")
	})

	// This is the v0 route, which we will re-implement for backwards compatibility
	// with the old Javascript server.
	r.POST("/uploadSensorDataNew", func(c *gin.Context) {
		SaveSensorDataHandler(c, sensorService)
	})

	return r
}

/* v0 routes, re-implemented for backwards compatibility before we add
   better-desigend routes. */
