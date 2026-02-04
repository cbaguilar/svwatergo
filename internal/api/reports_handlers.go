package api

import (
	"database/sql"
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/auth"
	"github.com/cbaguilar/svwatergo/internal/mail"
	"github.com/cbaguilar/svwatergo/internal/reports"
	"github.com/gin-gonic/gin"
)

type ReportsAPI struct {
	Store       *reports.Store
	Mail        mail.Sender
	AdminEmails []string
}

type createOperatorReportRequest struct {
	Title    string   `json:"title"`
	Body     string   `json:"body"`
	Status   string   `json:"status"`
	Severity string   `json:"severity"`
	Tags     []string `json:"tags"`
}

type updateOperatorReportRequest struct {
	Title    *string   `json:"title"`
	Body     *string   `json:"body"`
	Status   *string   `json:"status"`
	Severity *string   `json:"severity"`
	Tags     *[]string `json:"tags"`
}

func NewReportsAPI(store *reports.Store, sender mail.Sender, adminEmails []string) *ReportsAPI {
	return &ReportsAPI{Store: store, Mail: sender, AdminEmails: adminEmails}
}

func (a *ReportsAPI) CreateOperatorReport(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "reports store not configured", nil))
		return
	}
	var req createOperatorReportRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid json", gin.H{"err": err.Error()}))
		return
	}
	if strings.TrimSpace(req.Title) == "" || strings.TrimSpace(req.Body) == "" {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "title and body required", nil))
		return
	}

	site := strings.ToLower(strings.TrimSpace(c.Param("site")))

	createdByEmail := ""
	createdBySub := ""
	if id, ok := auth.IdentityFromContext(c.Request.Context()); ok {
		createdByEmail = id.Email
		createdBySub = id.Sub
	}

	report, err := a.Store.CreateOperatorReport(c.Request.Context(), reports.CreateOperatorReport{
		Site:           site,
		Title:          req.Title,
		Body:           req.Body,
		Status:         req.Status,
		Severity:       req.Severity,
		Tags:           req.Tags,
		CreatedByEmail: createdByEmail,
		CreatedBySub:   createdBySub,
	})
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "create report failed", gin.H{"err": err.Error()}))
		return
	}

	a.sendOperatorReportEmail(report)
	c.JSON(http.StatusCreated, report)
}

func (a *ReportsAPI) ListOperatorReports(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "reports store not configured", nil))
		return
	}
	site := strings.ToLower(strings.TrimSpace(c.Param("site")))
	limit := parseInt(c.DefaultQuery("limit", ""), 0)
	offset := parseInt(c.DefaultQuery("offset", ""), 0)
	status := strings.TrimSpace(c.Query("status"))

	reportsList, err := a.Store.ListOperatorReports(c.Request.Context(), reports.ListOperatorReports{
		Site:   site,
		Status: status,
		Limit:  limit,
		Offset: offset,
	})
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "list reports failed", gin.H{"err": err.Error()}))
		return
	}
	c.JSON(http.StatusOK, gin.H{"site": site, "reports": reportsList})
}

func (a *ReportsAPI) GetOperatorReport(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "reports store not configured", nil))
		return
	}
	site := strings.ToLower(strings.TrimSpace(c.Param("site")))
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid id", gin.H{"id": c.Param("id")}))
		return
	}
	report, err := a.Store.GetOperatorReport(c.Request.Context(), site, id)
	if err != nil {
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, errJSON("NotFound", "report not found", gin.H{"id": id}))
			return
		}
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "get report failed", gin.H{"err": err.Error()}))
		return
	}
	c.JSON(http.StatusOK, report)
}

func (a *ReportsAPI) UpdateOperatorReport(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "reports store not configured", nil))
		return
	}
	site := strings.ToLower(strings.TrimSpace(c.Param("site")))
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid id", gin.H{"id": c.Param("id")}))
		return
	}
	var req updateOperatorReportRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid json", gin.H{"err": err.Error()}))
		return
	}

	report, err := a.Store.UpdateOperatorReport(c.Request.Context(), site, id, reports.UpdateOperatorReport{
		Title:    req.Title,
		Body:     req.Body,
		Status:   req.Status,
		Severity: req.Severity,
		Tags:     req.Tags,
	})
	if err != nil {
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, errJSON("NotFound", "report not found", gin.H{"id": id}))
			return
		}
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "update report failed", gin.H{"err": err.Error()}))
		return
	}
	c.JSON(http.StatusOK, report)
}

func (a *ReportsAPI) DeleteOperatorReport(c *gin.Context) {
	if a.Store == nil {
		c.JSON(http.StatusNotImplemented, errJSON("NotImplemented", "reports store not configured", nil))
		return
	}
	site := strings.ToLower(strings.TrimSpace(c.Param("site")))
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid id", gin.H{"id": c.Param("id")}))
		return
	}
	if err := a.Store.DeleteOperatorReport(c.Request.Context(), site, id); err != nil {
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, errJSON("NotFound", "report not found", gin.H{"id": id}))
			return
		}
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "delete report failed", gin.H{"err": err.Error()}))
		return
	}
	c.Status(http.StatusNoContent)
}

func parseInt(raw string, def int) int {
	if strings.TrimSpace(raw) == "" {
		return def
	}
	v, err := strconv.Atoi(raw)
	if err != nil {
		return def
	}
	return v
}

func (a *ReportsAPI) sendOperatorReportEmail(report reports.OperatorReport) {
	if a.Mail == nil || len(a.AdminEmails) == 0 {
		return
	}
	subject := "Operator report: " + report.Site + " - " + report.Title
	body := strings.Builder{}
	body.WriteString("A new operator report was submitted.\n\n")
	body.WriteString("Site: " + report.Site + "\n")
	body.WriteString("Title: " + report.Title + "\n")
	body.WriteString("Status: " + report.Status + "\n")
	if report.Severity != "" {
		body.WriteString("Severity: " + report.Severity + "\n")
	}
	if len(report.Tags) > 0 {
		body.WriteString("Tags: " + strings.Join(report.Tags, ", ") + "\n")
	}
	body.WriteString("Created At: " + report.CreatedAt.UTC().Format(time.RFC3339) + "\n")
	if report.CreatedBy != nil && report.CreatedBy.Email != "" {
		body.WriteString("Created By: " + report.CreatedBy.Email + "\n")
	}
	body.WriteString("\n")
	body.WriteString(report.Body)

	if err := a.Mail.Send(mail.Message{
		To:       a.AdminEmails,
		Subject:  subject,
		TextBody: body.String(),
		ReplyTo:  strings.Join(a.AdminEmails, ", "),
	}); err != nil {
		log.Printf("operator report email failed: %v", err)
	}
}
