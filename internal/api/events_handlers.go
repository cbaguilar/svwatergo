package api

import (
	"net/http"
	"strings"

	"github.com/cbaguilar/svwatergo/internal/events"
	"github.com/gin-gonic/gin"
)

type EventsAPI struct {
	Svc *events.QueryService
}

func NewEventsAPI() *EventsAPI {
	svc, err := events.NewQueryServiceFromEnv()
	if err != nil {
		return &EventsAPI{Svc: nil}
	}
	return &EventsAPI{Svc: svc}
}

func (a *EventsAPI) QueryInterestingTimestamps(c *gin.Context) {
	site := strings.ToLower(c.Param("site"))
	if a == nil || a.Svc == nil {
		c.JSON(http.StatusServiceUnavailable, errJSON("Unavailable", "events query service unavailable", nil))
		return
	}

	var req events.QueryRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid json", gin.H{"err": err.Error()}))
		return
	}

	res, err := a.Svc.QuerySiteEvents(site, req)
	if err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", err.Error(), nil))
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{
			"site":     site,
			"returned": len(res.Timestamps),
		},
		"timestamps": res.Timestamps,
		"rows":       res.Rows,
	})
}
