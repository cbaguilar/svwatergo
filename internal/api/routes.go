package api

import (
	"net/http"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/auth"
	"github.com/cbaguilar/svwatergo/internal/mail"
	"github.com/cbaguilar/svwatergo/internal/metadata"
	"github.com/cbaguilar/svwatergo/internal/reports"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
)

func SetupRouter(ingestion *systemservice.DataIngestionService, reg systemservice.Registry, meta *metadata.Store, authn *auth.Auth, reportsStore *reports.Store, mailSender mail.Sender, adminEmails []string, ingestDisabled bool, readOnly bool) *gin.Engine {
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
		sites := v1.Group("/sites/:site")
		sites.GET("/state/latest", state.GetLatest)
		sites.GET("/state/stream", liveState.StreamLatest)
		sites.GET("/state", state.GetRange) // ?start=&end=&fields=&sample=&max_points=&smooth=&window=
		sites.GET("/metadata", site.GetMetadata)
		sites.GET("/coverage", site.GetCoverage)
		sites.GET("/series", site.GetSeries)
		sites.POST("/events/query", eventsAPI.QueryInterestingTimestamps)

		operatorReports := sites.Group("/operator-reports")
		if authn != nil {
			operatorReports.Use(authn.GinRequireAdmin())
		}
		if readOnly {
			disabled := func(c *gin.Context) {
				c.JSON(http.StatusServiceUnavailable, errJSON("ReadOnly", "server is in read-only mode", nil))
			}
			operatorReports.POST("", disabled)
			operatorReports.PUT("/:id", disabled)
			operatorReports.DELETE("/:id", disabled)
		} else {
			operatorReports.POST("", reportsAPI.CreateOperatorReport)
			operatorReports.PUT("/:id", reportsAPI.UpdateOperatorReport)
			operatorReports.DELETE("/:id", reportsAPI.DeleteOperatorReport)
		}
		operatorReports.GET("", reportsAPI.ListOperatorReports)
		operatorReports.GET("/:id", reportsAPI.GetOperatorReport)
	}

	/// This is the v0 route, which we will re-implement for backwards compatibility
	// with the old Javascript server.
	if ingestDisabled || readOnly {
		disabled := func(c *gin.Context) {
			msg := "ingestion is disabled"
			if readOnly {
				msg = "server is in read-only mode"
			}
			c.JSON(http.StatusServiceUnavailable, errJSON("Unavailable", msg, nil))
		}
		r.POST("/UploadDataNew", disabled)
		r.POST("/uploadSensorDataNew", disabled) // alias
	} else {
		r.POST("/UploadDataNew", SaveSensorDataHandler(ingestion))
		r.POST("/uploadSensorDataNew", SaveSensorDataHandler(ingestion)) // alias
	}

	return r
}
