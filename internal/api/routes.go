package api

import (
	"net/http"

	"github.com/cbaguilar/svwatergo/internal/auth"
	"github.com/cbaguilar/svwatergo/internal/mail"
	"github.com/cbaguilar/svwatergo/internal/metadata"
	"github.com/cbaguilar/svwatergo/internal/reports"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/gin-gonic/gin"
)

func SetupRouter(ingestion *systemservice.DataIngestionService, reg systemservice.Registry, meta *metadata.Store, authn *auth.Auth, reportsStore *reports.Store, mailSender mail.Sender, adminEmails []string) *gin.Engine {
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

	state := NewStateAPI(reg, meta)
	liveState := NewLiveStateAPI(reg, meta)
	site := NewSiteAPI(reg, meta)
	reportsAPI := NewReportsAPI(reportsStore, mailSender, adminEmails)
	ingestion.OnIngest = liveState.NotifySiteUpdated

	v1 := r.Group("/api/v1")
	if authn != nil {
		v1.Use(authn.GinMiddleware())
	}
	{
		sites := v1.Group("/sites/:site")
		sites.GET("/state/latest", state.GetLatest)
		sites.GET("/state/stream", liveState.StreamLatest)
		sites.GET("/state", state.GetRange) // ?start=&end=&fields=&sample=&max_points=&smooth=&window=
		sites.GET("/metadata", site.GetMetadata)
		sites.GET("/coverage", site.GetCoverage)
		sites.GET("/series", site.GetSeries)

		operatorReports := sites.Group("/operator-reports")
		if authn != nil {
			operatorReports.Use(authn.GinRequireAdmin())
		}
		operatorReports.POST("", reportsAPI.CreateOperatorReport)
		operatorReports.GET("", reportsAPI.ListOperatorReports)
		operatorReports.GET("/:id", reportsAPI.GetOperatorReport)
		operatorReports.PUT("/:id", reportsAPI.UpdateOperatorReport)
		operatorReports.DELETE("/:id", reportsAPI.DeleteOperatorReport)
	}

	/// This is the v0 route, which we will re-implement for backwards compatibility
	// with the old Javascript server.
	r.POST("/UploadDataNew", SaveSensorDataHandler(ingestion))
	r.POST("/uploadSensorDataNew", SaveSensorDataHandler(ingestion)) // alias

	return r
}
