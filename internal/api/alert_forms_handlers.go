package api

import (
	"bytes"
	"fmt"
	"net/http"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/go-pdf/fpdf"
)

type AlertFormsAPI struct{}

func NewAlertFormsAPI() *AlertFormsAPI {
	return &AlertFormsAPI{}
}

type generateAlertFormPDFRequest struct {
	AlertType          string   `json:"alertType"`
	AlertDetails       []string `json:"alertDetails"`
	CustomDetail       string   `json:"customDetail"`
	ResponseDetails    []string `json:"responseDetails"`
	DaysWaterLeft      *int     `json:"daysWaterLeft"`
	ReplacementDetails []string `json:"replacementDetails"`
	IssueDate          string   `json:"issueDate"`
	ResolveDate        string   `json:"resolveDate"`
	NoticeDate         string   `json:"noticeDate"`
	Substance          string   `json:"substance"`
	Incident           string   `json:"incident"`
	Location           string   `json:"location"`
	RecipientGroups    []string `json:"recipientGroups"`
}

var (
	alertDetailsCopy = map[string]string{
		"wellRepair":       "The well needs to be repaired",
		"connectionRepair": "The connection from the well to the treatment system needs to be repaired",
		"highBacteria":     "Regular testing showed that there were bacteria in the water system and this problem had to be addressed",
		"systemRepair":     "The water treatment system had to be repaired",
		"powerOut":         "The power is out and the pumps necessary for delivering water were not working properly and the problem had to be repaired",
		"custom":           "Custom Detail",
	}
	responseDetailsCopy = map[string]string{
		"daysWaterLeft": "Reduce Water: The Water Storage Tank has a limited number of days of supplies for normal usage.",
		"stopUsage":     "Stop drinking or cooking with tap water while the system is being cleaned.",
	}
	replacementDetailsCopy = map[string]string{
		"waterHaul":      "Expect that drinking water will be hauled to the site to replenish stored treated water",
		"useBottled":     "Until further notice, purchase and ONLY use bottled water",
		"bottleDelivery": "Bottled water will be delivered",
	}
	alertTypeTitles = map[string]string{
		"notProducing":  "Not Producing",
		"highNitrates":  "High Nitrates",
		"bacteria":      "Bacteria",
		"contamination": "Contamination",
		"resolved":      "Resolved",
	}
)

func (a *AlertFormsAPI) GeneratePDF(c *gin.Context) {
	var req generateAlertFormPDFRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "invalid json", gin.H{"err": err.Error()}))
		return
	}

	site := strings.ToLower(strings.TrimSpace(c.Param("site")))
	if site == "" {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "site is required", nil))
		return
	}
	if _, ok := alertTypeTitles[req.AlertType]; !ok {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "unsupported alertType", gin.H{"alertType": req.AlertType}))
		return
	}
	if len(req.RecipientGroups) == 0 {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "at least one recipient group is required", nil))
		return
	}
	if hasKey(req.ResponseDetails, "daysWaterLeft") && (req.DaysWaterLeft == nil || *req.DaysWaterLeft < 0) {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "daysWaterLeft must be provided for daysWaterLeft response detail", nil))
		return
	}
	if hasKey(req.AlertDetails, "custom") && strings.TrimSpace(req.CustomDetail) == "" {
		c.JSON(http.StatusBadRequest, errJSON("BadRequest", "customDetail is required when custom alert detail is selected", nil))
		return
	}

	pdfBytes, err := renderAlertFormPDF(site, req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "failed to render pdf", gin.H{"err": err.Error()}))
		return
	}

	filename := fmt.Sprintf("alert-form-%s-%s.pdf", req.AlertType, time.Now().UTC().Format("20060102-150405"))
	c.Header("Content-Type", "application/pdf")
	c.Header("Content-Disposition", fmt.Sprintf("attachment; filename=%q", filepath.Base(filename)))
	c.Data(http.StatusOK, "application/pdf", pdfBytes)
}

func renderAlertFormPDF(site string, req generateAlertFormPDFRequest) ([]byte, error) {
	pdf := fpdf.New("P", "mm", "Letter", "")
	pdf.SetMargins(15, 15, 15)
	pdf.SetAutoPageBreak(true, 15)
	pdf.AddPage()

	pdf.SetFont("Helvetica", "B", 16)
	pdf.CellFormat(0, 8, "WaTeR System Alert Form", "", 1, "L", false, 0, "")
	pdf.SetFont("Helvetica", "", 11)
	pdf.CellFormat(0, 6, "Site: "+strings.ToUpper(site), "", 1, "L", false, 0, "")
	pdf.CellFormat(0, 6, "Alert Type: "+alertTypeTitles[req.AlertType], "", 1, "L", false, 0, "")
	pdf.CellFormat(0, 6, "Generated: "+time.Now().UTC().Format(time.RFC3339), "", 1, "L", false, 0, "")
	pdf.Ln(2)

	switch req.AlertType {
	case "notProducing", "resolved":
		writeSection(pdf, "Alert Details", describeAlertDetails(req.AlertDetails, req.CustomDetail))
		writeSection(pdf, sectionTitleForResponse(req.AlertType), describeResponseDetails(req.ResponseDetails, req.DaysWaterLeft))
		writeSection(pdf, "Replacement Details", describeReplacementDetails(req.ReplacementDetails))
		if strings.TrimSpace(req.NoticeDate) != "" {
			writeSection(pdf, "Notice Date", []string{req.NoticeDate})
		}
	case "highNitrates", "bacteria":
		writeSection(pdf, "Issue Date", []string{fallbackValue(req.IssueDate)})
		writeSection(pdf, "Expected Resolve Date", []string{fallbackValue(req.ResolveDate)})
	case "contamination":
		writeSection(pdf, "Issue Date", []string{fallbackValue(req.IssueDate)})
		writeSection(pdf, "Expected Resolve Date", []string{fallbackValue(req.ResolveDate)})
		writeSection(pdf, "Suspected Substance", []string{fallbackValue(req.Substance)})
		writeSection(pdf, "Incident Type", []string{fallbackValue(req.Incident)})
		writeSection(pdf, "Incident Location", []string{fallbackValue(req.Location)})
	}

	writeSection(pdf, "Recipient Groups", nonEmptyOrFallback(req.RecipientGroups))

	var out bytes.Buffer
	if err := pdf.Output(&out); err != nil {
		return nil, err
	}
	return out.Bytes(), nil
}

func writeSection(pdf *fpdf.Fpdf, title string, lines []string) {
	pdf.SetFont("Helvetica", "B", 12)
	pdf.CellFormat(0, 7, title, "", 1, "L", false, 0, "")
	pdf.SetFont("Helvetica", "", 11)
	for _, line := range nonEmptyOrFallback(lines) {
		pdf.MultiCell(0, 6, " - "+line, "", "L", false)
	}
	pdf.Ln(1)
}

func describeAlertDetails(keys []string, customDetail string) []string {
	out := make([]string, 0, len(keys)+1)
	for _, key := range keys {
		if key == "custom" {
			if trimmed := strings.TrimSpace(customDetail); trimmed != "" {
				out = append(out, "Custom Detail: "+trimmed)
				continue
			}
		}
		if label, ok := alertDetailsCopy[key]; ok {
			out = append(out, label)
		}
	}
	return out
}

func describeResponseDetails(keys []string, daysWaterLeft *int) []string {
	out := make([]string, 0, len(keys))
	for _, key := range keys {
		if key == "daysWaterLeft" && daysWaterLeft != nil {
			out = append(out, fmt.Sprintf("Reduce Water: The Water Storage Tank has %d days of supplies for normal usage.", *daysWaterLeft))
			continue
		}
		if label, ok := responseDetailsCopy[key]; ok {
			out = append(out, label)
		}
	}
	return out
}

func describeReplacementDetails(keys []string) []string {
	out := make([]string, 0, len(keys))
	for _, key := range keys {
		if label, ok := replacementDetailsCopy[key]; ok {
			out = append(out, label)
		}
	}
	return out
}

func sectionTitleForResponse(alertType string) string {
	if alertType == "resolved" {
		return "Resolution Details"
	}
	return "Response Details"
}

func hasKey(items []string, key string) bool {
	for _, item := range items {
		if item == key {
			return true
		}
	}
	return false
}

func fallbackValue(value string) string {
	v := strings.TrimSpace(value)
	if v == "" {
		return "(not provided)"
	}
	return v
}

func nonEmptyOrFallback(lines []string) []string {
	out := make([]string, 0, len(lines))
	for _, line := range lines {
		if trimmed := strings.TrimSpace(line); trimmed != "" {
			out = append(out, trimmed)
		}
	}
	if len(out) == 0 {
		return []string{"(none)"}
	}
	return out
}
