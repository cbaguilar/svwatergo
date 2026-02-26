package api

import (
	"net/http"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/analytics"
	"github.com/cbaguilar/svwatergo/internal/audio"
	"github.com/cbaguilar/svwatergo/internal/auth"
	"github.com/cbaguilar/svwatergo/internal/mail"
	"github.com/cbaguilar/svwatergo/internal/metadata"
	"github.com/cbaguilar/svwatergo/internal/reports"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
)

func SetupRouter(ingestion *systemservice.DataIngestionService, reg systemservice.Registry, meta *metadata.Store, authn *auth.Auth, reportsStore *reports.Store, audioStore *audio.Store, mailSender mail.Sender, adminEmails []string, ingestDisabled bool, readOnly bool) *gin.Engine {
	// Disable Console Color
	// gin.DisableConsoleColor()
	r := gin.Default()
	r.Use(cors.New(cors.Config{
		AllowOriginFunc: func(origin string) bool {
			o := strings.ToLower(strings.TrimSpace(origin))
			switch o {
			case "http://localhost:3000",
				"https://localhost:3000",
				"http://localhost:5173",
				"https://localhost:5173",
				"http://127.0.0.1:3000",
				"https://127.0.0.1:3000",
				"http://127.0.0.1:5173",
				"https://127.0.0.1:5173",
				"https://new.svwaternet.org",
				"https://svwaternet.org",
				"https://www.svwaternet.org",
				"http://svwaternet.org:3000":
				return true
			default:
				return false
			}
		},
		AllowMethods:     []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Accept", "Authorization"},
		ExposeHeaders:    []string{"Content-Length"},
		AllowCredentials: false,
		MaxAge:           12 * time.Hour,
	}))

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
	audioAPI := NewAudioAPI(audioStore)
	analyticsStore := analytics.NewStore()
	analyticsRunner := analytics.NewRunner(analyticsStore)
	analyticsAPI := NewAnalyticsAPI(analyticsStore, analyticsRunner)
	eventsAPI := NewEventsAPI()
	authAPI := NewAuthAPI(authn)
	ingestion.OnIngest = liveState.NotifySiteUpdated

	authGroup := r.Group("/api/v1/auth")
	{
		authGroup.GET("/config", authAPI.GetConfig)
		authGroup.POST("/google/exchange", authAPI.ExchangeGoogle)
		if authn != nil {
			authGroup.GET("/me", authn.GinMiddleware(), authAPI.Me)
		} else {
			authGroup.GET("/me", authAPI.Me)
		}
	}

	v1 := r.Group("/api/v1")
	if authn != nil {
		v1.Use(authn.GinMiddleware())
	}
	{
		analyticsGroup := v1.Group("/analytics")
		analyticsGroup.POST("/feature-runs", analyticsAPI.CreateFeatureRun)
		analyticsGroup.POST("/pca-runs", analyticsAPI.CreatePCARun)
		analyticsGroup.POST("/audio-align-runs", analyticsAPI.CreateAudioAlignPLCRun)
		analyticsGroup.GET("/jobs", analyticsAPI.ListJobs)
		analyticsGroup.GET("/jobs/:id", analyticsAPI.GetJob)

		audioGroup := v1.Group("/audio")
		audioGroup.GET("/sources", audioAPI.ListSources)
		audioGroup.GET("/artifacts", audioAPI.ListArtifacts)
		audioGroup.GET("/artifacts/:id", audioAPI.GetArtifact)
		if readOnly {
			disabled := func(c *gin.Context) {
				c.JSON(http.StatusServiceUnavailable, errJSON("ReadOnly", "server is in read-only mode", nil))
			}
			audioGroup.POST("/sources", disabled)
			audioGroup.POST("/artifacts", disabled)
		} else {
			audioGroup.POST("/sources", audioAPI.UpsertSource)
			audioGroup.POST("/artifacts", audioAPI.UpsertArtifact)
		}

		sites := v1.Group("/sites/:site")
		sites.GET("/state/latest", state.GetLatest)
		sites.GET("/state/stream", liveState.StreamLatest)
		sites.GET("/state", state.GetRange) // ?start=&end=&fields=&sample=&max_points=&smooth=&window=
		sites.GET("/metadata", site.GetMetadata)
		sites.GET("/coverage", site.GetCoverage)
		sites.GET("/series", site.GetSeries)
		sites.GET("/summary/daily", site.GetDailySummary)
		sites.GET("/forecast/next-state", site.GetNextStateForecast)
		sites.POST("/events/query", eventsAPI.QueryInterestingTimestamps)

		operatorReports := sites.Group("/operator-reports")
		operatorReportsAdmin := sites.Group("/operator-reports")
		if authn != nil {
			operatorReportsAdmin.Use(authn.GinRequireAdmin())
		}
		if readOnly {
			disabled := func(c *gin.Context) {
				c.JSON(http.StatusServiceUnavailable, errJSON("ReadOnly", "server is in read-only mode", nil))
			}
			operatorReportsAdmin.POST("", disabled)
			operatorReportsAdmin.PUT("/:id", disabled)
			operatorReportsAdmin.DELETE("/:id", disabled)
		} else {
			operatorReportsAdmin.POST("", reportsAPI.CreateOperatorReport)
			operatorReportsAdmin.PUT("/:id", reportsAPI.UpdateOperatorReport)
			operatorReportsAdmin.DELETE("/:id", reportsAPI.DeleteOperatorReport)
		}
		operatorReports.GET("", reportsAPI.ListOperatorReports)
		operatorReports.GET("/:id", reportsAPI.GetOperatorReport)
	}

	/// This is the v0 route, which we will re-implement for backwards compatibility
	// with the old Javascript server.
	if ingestDisabled {
		disabled := func(c *gin.Context) {
			c.JSON(http.StatusServiceUnavailable, errJSON("Unavailable", "ingestion is disabled", nil))
		}
		r.POST("/UploadDataNew", disabled)
		r.POST("/uploadDataNew", disabled)       // alias for legacy mirror path
		r.POST("/uploadSensorDataNew", disabled) // alias
	} else if readOnly {
		shadowIngestion := *ingestion
		shadowIngestion.DryRun = true
		shadowIngestion.OnIngest = nil
		shadow := SaveSensorDataHandler(&shadowIngestion)
		r.POST("/UploadDataNew", shadow)
		r.POST("/uploadDataNew", shadow)       // alias for legacy mirror path
		r.POST("/uploadSensorDataNew", shadow) // alias
	} else {
		r.POST("/UploadDataNew", SaveSensorDataHandler(ingestion))
		r.POST("/uploadDataNew", SaveSensorDataHandler(ingestion))       // alias for legacy mirror path
		r.POST("/uploadSensorDataNew", SaveSensorDataHandler(ingestion)) // alias
	}

	return r
}
