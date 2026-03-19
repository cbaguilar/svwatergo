package api

import (
	"bytes"
	"fmt"
	"math"
	"net/http"
	"path/filepath"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/metadata"
	"github.com/gin-gonic/gin"
	"github.com/go-pdf/fpdf"
)

type AlertFormsAPI struct {
	Meta *metadata.Store
}

func NewAlertFormsAPI(meta *metadata.Store) *AlertFormsAPI {
	return &AlertFormsAPI{Meta: meta}
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

type alertSiteProfile struct {
	StreetAddr   string
	SystemID     string
	ContactNames string
	ContactPhone string
}

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

	pdfBytes, err := renderAlertFormPDF(a.Meta, site, req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("Internal", "failed to render pdf", gin.H{"err": err.Error()}))
		return
	}

	filename := fmt.Sprintf("alert-form-%s-%s.pdf", req.AlertType, time.Now().UTC().Format("20060102-150405"))
	c.Header("Content-Type", "application/pdf")
	c.Header("Content-Disposition", fmt.Sprintf("attachment; filename=%q", filepath.Base(filename)))
	c.Data(http.StatusOK, "application/pdf", pdfBytes)
}

func renderAlertFormPDF(meta *metadata.Store, site string, req generateAlertFormPDFRequest) ([]byte, error) {
	pdf := fpdf.New("P", "mm", "Letter", "")
	pdf.SetMargins(15, 15, 15)
	pdf.SetAutoPageBreak(true, 15)
	pdf.AddPage()

	if req.AlertType == "resolved" {
		return renderResolvedAlertStyledPDF(pdf, meta, site, req)
	}

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

func renderResolvedAlertStyledPDF(pdf *fpdf.Fpdf, meta *metadata.Store, site string, req generateAlertFormPDFRequest) ([]byte, error) {
	left, _, right, _ := pdf.GetMargins()
	pageW, pageH := pdf.GetPageSize()
	contentW := pageW - left - right
	profile := alertProfileForSite(meta, site)

	drawHeaderBanner(pdf, left, contentW)
	drawHeadlineBox(pdf, left, contentW, "DRINKING WATER PROBLEM CORRECTED")

	pdf.SetFont("Helvetica", "", 11)
	pdf.MultiCell(contentW, 6, buildResolvedIntro(profile, req), "", "L", false)
	pdf.Ln(1)
	writeBulletList(pdf, describeAlertDetailsResolved(req.AlertDetails, req.CustomDetail))
	pdf.Ln(1)

	pdf.MultiCell(contentW, 6, "You were advised on that date to do one of the following:", "", "L", false)
	pdf.Ln(1)
	writeBulletList(pdf, buildResolvedActions(req))
	pdf.Ln(1)

	pdf.MultiCell(contentW, 6, buildResolvedClosing(), "", "L", false)
	pdf.Ln(2)

	writeContactSection(pdf, profile)
	drawResolvedFooter(pdf, left, pageW-right, pageH, profile, req)

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

func drawHeaderBanner(pdf *fpdf.Fpdf, left, width float64) {
	startY := pdf.GetY()
	pdf.SetFillColor(245, 237, 145)
	pdf.Rect(left+8, startY, width-16, 7, "F")
	pdf.SetXY(left, startY+0.6)
	pdf.SetFont("Helvetica", "B", 12)
	pdf.CellFormat(width, 5, "IMPORTANT INFORMATION ABOUT YOUR DRINKING WATER", "", 1, "C", false, 0, "")
	pdf.SetFont("Helvetica", "", 10)
	pdf.CellFormat(width, 5, "Este informe contiene informacion muy importante sobre su agua potable.", "", 1, "C", false, 0, "")
	pdf.Ln(4)
}

func drawHeadlineBox(pdf *fpdf.Fpdf, left, width float64, headline string) {
	startY := pdf.GetY()
	boxH := 18.0
	pdf.Rect(left+5, startY, width-10, boxH, "")
	pdf.SetXY(left+10, startY+3)
	pdf.SetFont("Helvetica", "B", 15)
	pdf.MultiCell(width-20, 6, headline, "", "C", false)
	pdf.SetY(startY + boxH + 6)
}

func buildResolvedIntro(profile alertSiteProfile, req generateAlertFormPDFRequest) string {
	noticeDate := fallbackValue(req.NoticeDate)
	return fmt.Sprintf(
		"Dear residents of %s:\nYou were notified on %s that the water treatment system (ID: %s) had to stop producing because of the following:",
		profile.StreetAddr,
		noticeDate,
		profile.SystemID,
	)
}

func buildResolvedActions(req generateAlertFormPDFRequest) []string {
	lines := describeResponseDetailsResolved(req.ResponseDetails, req.DaysWaterLeft)
	lines = append(lines, describeReplacementDetailsResolved(req.ReplacementDetails)...)
	return lines
}

func buildResolvedClosing() string {
	return "We are pleased to report that the problem has now been corrected and treated water service and storage is back to normal. You may now drink the water. It is not necessary to restrict your water use. We apologize for any inconvenience and thank you for your patience."
}

func writeContactSection(pdf *fpdf.Fpdf, profile alertSiteProfile) {
	pdf.SetFont("Helvetica", "", 11)
	contactCopy := "This notice is being sent to you by the Project Team at UCLA Smart Water Treatment System. You can reach us to discuss questions about the Water Treatment System by any of the following methods:"
	pdf.MultiCell(0, 6, contactCopy, "", "L", false)
	pdf.Ln(1)
	lines := []string{
		"Send us a message via the UCLA Water Treatment System Website: https://svwaternet.org/",
		"Text or call us at (323) 364-5535",
		"Email us at: svwaternet@gmail.com",
	}
	writeBulletList(pdf, lines)
	pdf.Ln(2)
	pdf.MultiCell(0, 6, "If the problem is a well repair or water distribution system repair, please contact the owner for further information on time to repair.", "", "L", false)
	pdf.Ln(1)
	pdf.MultiCell(0, 6, profile.ContactNames, "", "L", false)
	pdf.MultiCell(0, 6, profile.ContactPhone, "", "L", false)
}

func drawResolvedFooter(pdf *fpdf.Fpdf, left, right, pageH float64, profile alertSiteProfile, req generateAlertFormPDFRequest) {
	footerY := math.Max(pdf.GetY()+6, pageH-28)
	if footerY > pageH-22 {
		pdf.AddPage()
		footerY = pageH - 28
	}
	pdf.SetY(footerY)
	pdf.SetFont("Helvetica", "", 11)
	pdf.SetX(left)
	pdf.CellFormat((right-left)/2, 6, "State Water System ID#: "+profile.SystemID, "", 0, "L", false, 0, "")
	pdf.CellFormat((right-left)/2, 6, "Date Distributed: "+fallbackValue(req.NoticeDate), "", 1, "R", false, 0, "")
}

func bulletPrefix(line string) string {
	return "- " + line
}

func writeBulletList(pdf *fpdf.Fpdf, lines []string) {
	pdf.SetFont("Helvetica", "", 11)
	for _, line := range nonEmptyOrFallback(lines) {
		pdf.MultiCell(0, 6, bulletPrefix(line), "", "L", false)
	}
}

func describeAlertDetailsResolved(keys []string, customDetail string) []string {
	out := make([]string, 0, len(keys)+1)
	for _, key := range keys {
		if key == "custom" {
			if trimmed := strings.TrimSpace(customDetail); trimmed != "" {
				out = append(out, trimmed)
			}
			continue
		}
		switch key {
		case "wellRepair":
			out = append(out, "The well needed to be repaired")
		case "connectionRepair":
			out = append(out, "The connection from the well to the treatment system needed to be repaired")
		case "highBacteria":
			out = append(out, "Regular testing showed that there were bacteria in the water system that had to be flushed out")
		case "systemRepair":
			out = append(out, "The water treatment system had to be repaired")
		case "powerOut":
			out = append(out, "The power was out and the pumps necessary for delivering water were not working")
		}
	}
	return out
}

func describeResponseDetailsResolved(keys []string, daysWaterLeft *int) []string {
	out := make([]string, 0, len(keys))
	for _, key := range keys {
		switch key {
		case "daysWaterLeft":
			if daysWaterLeft != nil {
				dayWord := "days"
				if *daysWaterLeft == 1 {
					dayWord = "day"
				}
				out = append(out, fmt.Sprintf("Conserve water as there was only enough storage for %d %s of normal service", *daysWaterLeft, dayWord))
			}
		case "stopUsage":
			out = append(out, "Stop using the water while the system was being flushed.")
		}
	}
	return out
}

func describeReplacementDetailsResolved(keys []string) []string {
	out := make([]string, 0, len(keys))
	for _, key := range keys {
		switch key {
		case "waterHaul":
			out = append(out, "Expect that drinking water will be hauled to the site to replenish stored treated water and that normal water service will be resumed.")
		case "useBottled":
			out = append(out, "Until further notice, please PURCHASE AND only use bottled water.")
		case "bottleDelivery":
			out = append(out, "Bottled water will be delivered to you until service resumes.")
		}
	}
	return out
}

func alertProfileForSite(meta *metadata.Store, site string) alertSiteProfile {
	cfg, ok := meta.Get(site)
	if ok {
		profile := alertSiteProfile{
			StreetAddr:   strings.TrimSpace(cfg.AlertStreetAddr),
			SystemID:     strings.TrimSpace(cfg.StateWaterSystemID),
			ContactNames: strings.TrimSpace(cfg.AlertContactNames),
			ContactPhone: strings.TrimSpace(cfg.AlertContactPhone),
		}
		if profile.StreetAddr == "" {
			if v := strings.TrimSpace(cfg.DisplayName); v != "" {
				profile.StreetAddr = v
			} else if v := strings.TrimSpace(cfg.FormalName); v != "" {
				profile.StreetAddr = v
			} else {
				profile.StreetAddr = strings.TrimSpace(cfg.Site)
			}
		}
		if profile.SystemID == "" {
			profile.SystemID = "N/A"
		}
		if profile.ContactNames == "" {
			profile.ContactNames = "Water system owner contact not configured."
		}
		return profile
	}
	return alertSiteProfile{
		StreetAddr:   strings.TrimSpace(site),
		SystemID:     "N/A",
		ContactNames: "Water system owner contact not configured.",
		ContactPhone: "",
	}
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
