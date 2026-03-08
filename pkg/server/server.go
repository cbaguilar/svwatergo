package server

import (
	"context"
	"fmt"
	"log"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/config"
	"github.com/cbaguilar/svwatergo/internal/api"
	"github.com/cbaguilar/svwatergo/internal/audio"
	"github.com/cbaguilar/svwatergo/internal/auth"
	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/cbaguilar/svwatergo/internal/mail"
	"github.com/cbaguilar/svwatergo/internal/metadata"
	"github.com/cbaguilar/svwatergo/internal/reports"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/cbaguilar/svwatergo/internal/systemservice/bluerock"
	"github.com/cbaguilar/svwatergo/internal/systemservice/pryorfarm"
	"github.com/cbaguilar/svwatergo/internal/systemservice/santateresa"
	"github.com/cbaguilar/svwatergo/internal/users"
)

type Server struct {
	config *Config
}

type Config struct {
	Port string
}

const (
	staleDataThreshold      = 30 * time.Minute
	staleDataCheckInterval  = 5 * time.Minute
	staleDataRepeatInterval = 1 * time.Hour
	plcAlarmCheckInterval   = 1 * time.Minute
	plcAlarmRepeatInterval  = 1 * time.Hour
)

var runtimePLCAlarmStateStore *plcAlarmStateStore

func New(cfg *Config) *Server {
	return &Server{
		config: cfg,
	}
}

func (s *Server) Start() error {
	if err := config.LoadDotEnv(".env"); err != nil {
		log.Printf("Failed to load .env: %v", err)
	}

	// Here you would initialize and add your specific SystemManagers
	// e.g., ourIngestionService.Managers["bluerock"] = bluerock.NewBluerockManager(...)

	dbClient, err := loadDBClientFromEnv()
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}

	reg := systemservice.NewRegistry(map[string]systemservice.SystemManager{
		"bluerock":    bluerock.NewBluerockManager(*dbClient),
		"pryorfarm":   pryorfarm.NewPryorFarmManager(*dbClient),
		"santateresa": santateresa.NewSantaTeresaManager(*dbClient)})

	ing := &systemservice.DataIngestionService{
		Reg: reg,
	}

	metaStore, err := metadata.LoadDir("config/sites")
	if err != nil {
		log.Fatalf("Failed to load site metadata: %v", err)
	}

	reportsStore := reports.NewStore(dbClient)
	if err := reportsStore.EnsureSchema(context.Background()); err != nil {
		log.Fatalf("Failed to ensure reports schema: %v", err)
	}
	audioStore := audio.NewStore(dbClient)
	if err := audioStore.EnsureSchema(context.Background()); err != nil {
		log.Fatalf("Failed to ensure audio schema: %v", err)
	}
	usersStore := users.NewStore(dbClient)
	if err := usersStore.EnsureSchema(context.Background()); err != nil {
		log.Fatalf("Failed to ensure users schema: %v", err)
	}

	var authn *auth.Auth
	adminEmails := auth.AdminEmailsFromEnv()
	if strings.TrimSpace(os.Getenv("AUTH_DISABLED")) == "" {
		authn = auth.MustNewFromEnv(context.Background())
		authn.SetUserStore(usersStore)
		bootstrapUsers(context.Background(), usersStore, authn.AdminEmails(), authn.AllowedEmails())
		if len(authn.AdminEmails()) > 0 {
			adminEmails = authn.AdminEmails()
		}
	}

	var mailSender mail.Sender
	if sender, err := mail.NewSMTPSenderFromEnv(); err != nil {
		log.Printf("SMTP not configured: %v", err)
	} else {
		mailSender = sender
	}
	runtimePLCAlarmStateStore = newPLCAlarmStateStore(dbClient)
	if err := runtimePLCAlarmStateStore.EnsureSchema(context.Background()); err != nil {
		log.Fatalf("Failed to ensure plc alarm state schema: %v", err)
	}

	checkStartupStaleData(ing.Reg, mailSender, adminEmails, staleDataThreshold)
	startStaleDataMonitor(ing.Reg, mailSender, adminEmails, staleDataThreshold, staleDataCheckInterval, staleDataRepeatInterval)
	startPLCAlarmMonitor(ing.Reg, mailSender, adminEmails, plcAlarmCheckInterval, plcAlarmRepeatInterval)

	ingestDisabled := envEnabled("INGEST_DISABLED")
	readOnly := envEnabled("READ_ONLY_MODE")
	if readOnly {
		log.Printf("READ_ONLY_MODE enabled: mutating API routes are disabled")
	}
	if ingestDisabled {
		log.Printf("INGEST_DISABLED enabled: upload ingestion endpoints are disabled")
	}

	router := api.SetupRouter(ing, ing.Reg, metaStore, authn, reportsStore, audioStore, usersStore, mailSender, adminEmails, ingestDisabled, readOnly, dbClient)
	log.Printf("Server starting on port %s", s.config.Port)
	return router.Run(":" + s.config.Port)
}

func bootstrapUsers(ctx context.Context, usersStore *users.Store, admins []string, allowed []string) {
	if usersStore == nil {
		return
	}
	for _, email := range allowed {
		if err := usersStore.UpsertUserByEmail(ctx, email, users.RoleLabMember); err != nil {
			log.Printf("users bootstrap failed for allowed email %q: %v", email, err)
		}
	}
	for _, email := range admins {
		if err := usersStore.UpsertUserByEmail(ctx, email, users.RoleAdmin); err != nil {
			log.Printf("users bootstrap failed for admin email %q: %v", email, err)
		}
	}
}

type staleMonitorState struct {
	lastAlertAt time.Time
	lastSeenTS  time.Time
}

type plcAlarmMonitorState struct {
	lastAlertAt        time.Time
	lastSeenTS         time.Time
	lastAlarmOn        bool
	lastAlarmKey       string
	messageCount       int64
	incidentReportedAt time.Time
	incidentResolvedAt time.Time
}

func checkStartupStaleData(reg systemservice.Registry, mailSender mail.Sender, recipients []string, maxAge time.Duration) {
	if reg == nil || maxAge <= 0 {
		return
	}

	now := time.Now().UTC()
	sites := reg.Sites()
	sort.Strings(sites)

	type staleSite struct {
		site string
		ts   time.Time
		age  time.Duration
	}
	stale := make([]staleSite, 0)

	for _, site := range sites {
		mgr, ok := reg.Get(site)
		if !ok || mgr == nil {
			continue
		}

		data, err := mgr.GetLatest()
		if err != nil {
			log.Printf("startup stale-data check skipped for %s: GetLatest failed: %v", site, err)
			continue
		}

		ts, ok := latestTimestamp(data)
		if !ok {
			log.Printf("startup stale-data check skipped for %s: no recordtime/plctime timestamp", site)
			continue
		}

		age := now.Sub(ts.UTC())
		if age > maxAge {
			stale = append(stale, staleSite{site: site, ts: ts.UTC(), age: age})
		}
	}

	if len(stale) == 0 {
		return
	}

	body := strings.Builder{}
	body.WriteString("Startup stale data alert\n\n")
	body.WriteString(fmt.Sprintf("Threshold: %s\n", maxAge))
	body.WriteString(fmt.Sprintf("Checked At: %s\n\n", now.Format(time.RFC3339)))
	body.WriteString("Sites older than threshold:\n")
	for _, item := range stale {
		body.WriteString(fmt.Sprintf("- %s: last=%s age=%s\n", item.site, item.ts.Format(time.RFC3339), item.age.Round(time.Second)))
	}

	log.Printf("startup stale-data alert: %d site(s) exceed %s\n%s", len(stale), maxAge, body.String())

	if mailSender == nil || len(recipients) == 0 {
		return
	}

	if err := mailSender.Send(mail.Message{
		To:       recipients,
		Subject:  fmt.Sprintf("SVWaterGo startup stale data alert (%d site(s))", len(stale)),
		TextBody: body.String(),
		ReplyTo:  strings.Join(recipients, ", "),
	}); err != nil {
		log.Printf("startup stale-data email failed: %v", err)
	}
}

func startStaleDataMonitor(reg systemservice.Registry, mailSender mail.Sender, recipients []string, maxAge, checkEvery, repeatEvery time.Duration) {
	if reg == nil || maxAge <= 0 || checkEvery <= 0 {
		return
	}
	go func() {
		ticker := time.NewTicker(checkEvery)
		defer ticker.Stop()

		stateBySite := map[string]staleMonitorState{}
		for range ticker.C {
			checkPeriodicStaleData(reg, mailSender, recipients, maxAge, repeatEvery, stateBySite)
		}
	}()
}

func checkPeriodicStaleData(reg systemservice.Registry, mailSender mail.Sender, recipients []string, maxAge, repeatEvery time.Duration, stateBySite map[string]staleMonitorState) {
	now := time.Now().UTC()
	sites := reg.Sites()
	sort.Strings(sites)
	activeSites := make(map[string]struct{}, len(sites))

	for _, site := range sites {
		activeSites[site] = struct{}{}
		mgr, ok := reg.Get(site)
		if !ok || mgr == nil {
			continue
		}

		data, err := mgr.GetLatest()
		if err != nil {
			log.Printf("periodic stale-data check skipped for %s: GetLatest failed: %v", site, err)
			continue
		}

		ts, ok := latestTimestamp(data)
		if !ok {
			log.Printf("periodic stale-data check skipped for %s: no recordtime/plctime timestamp", site)
			continue
		}
		ts = ts.UTC()
		age := now.Sub(ts)
		prev := stateBySite[site]

		if age <= maxAge {
			if !prev.lastAlertAt.IsZero() {
				log.Printf("stale-data recovered for %s: last=%s age=%s", site, ts.Format(time.RFC3339), age.Round(time.Second))
			}
			delete(stateBySite, site)
			continue
		}

		shouldAlert := prev.lastAlertAt.IsZero()
		if !shouldAlert && repeatEvery > 0 && now.Sub(prev.lastAlertAt) >= repeatEvery {
			shouldAlert = true
		}
		if !shouldAlert && !prev.lastSeenTS.Equal(ts) && prev.lastSeenTS.Before(ts) {
			// Data advanced but is still stale; keep state fresh without forcing an extra alert.
			prev.lastSeenTS = ts
			stateBySite[site] = prev
			continue
		}
		if !shouldAlert {
			continue
		}

		isRepeat := !prev.lastAlertAt.IsZero()
		prev.lastAlertAt = now
		prev.lastSeenTS = ts
		stateBySite[site] = prev

		sendStaleSiteAlert(mailSender, recipients, site, ts, age, maxAge, now, repeatEvery, isRepeat)
	}

	for site := range stateBySite {
		if _, ok := activeSites[site]; !ok {
			delete(stateBySite, site)
		}
	}
}

func sendStaleSiteAlert(mailSender mail.Sender, recipients []string, site string, ts time.Time, age, maxAge time.Duration, checkedAt time.Time, repeatEvery time.Duration, isRepeat bool) {
	subjectPrefix := "SVWaterGo stale data alert"
	if isRepeat {
		subjectPrefix = "SVWaterGo stale data reminder"
	}
	siteLabel := formatSiteAlertName(site)
	ageMinutes := int(age.Round(time.Minute) / time.Minute)
	if ageMinutes < 1 {
		ageMinutes = 1
	}
	nextReminderText := "one hour"
	if repeatEvery > 0 && repeatEvery != time.Hour {
		nextReminderText = repeatEvery.String()
	}
	body := strings.Builder{}
	body.WriteString("Admin!\n\n")
	body.WriteString(fmt.Sprintf("The WaTeR device %s has not sent data in last  %d minutes\n", siteLabel, ageMinutes))
	body.WriteString("Please check whether the device is ON and a connection can be made to the device.")
	if repeatEvery > 0 {
		body.WriteString(fmt.Sprintf(" An automated alert message will be generated upon next reminder event in %s.", nextReminderText))
	}
	body.WriteString("\n\n")
	body.WriteString("This communication is the property of UCLA WaTeR Group and may contain confidential information. Unauthorized use of this communication is prohibited. If you have received this communication in error, please immediately notify by reply email and destroy all copies of the communication and any attachments.\n\n")
	body.WriteString("UCLA WaTeR Group,\n")
	body.WriteString("5531-E Boelter Hall,\n")
	body.WriteString("University of California Los Angeles, CA 9\n\n")
	body.WriteString(fmt.Sprintf("Site key: %s\n", site))
	body.WriteString(fmt.Sprintf("Last Data Time (UTC): %s\n", ts.Format(time.RFC3339)))
	body.WriteString(fmt.Sprintf("Data Age: %s\n", age.Round(time.Second)))
	body.WriteString(fmt.Sprintf("Threshold: %s\n", maxAge))
	body.WriteString(fmt.Sprintf("Checked At (UTC): %s\n", checkedAt.Format(time.RFC3339)))

	log.Printf("stale-data alert for %s: last=%s age=%s threshold=%s", site, ts.Format(time.RFC3339), age.Round(time.Second), maxAge)

	if mailSender == nil || len(recipients) == 0 {
		return
	}
	if err := mailSender.Send(mail.Message{
		To:       recipients,
		Subject:  fmt.Sprintf("%s: %s (age %s)", subjectPrefix, site, age.Round(time.Minute)),
		TextBody: body.String(),
		ReplyTo:  strings.Join(recipients, ", "),
	}); err != nil {
		log.Printf("stale-data email failed for %s: %v", site, err)
	}
}

func startPLCAlarmMonitor(reg systemservice.Registry, mailSender mail.Sender, recipients []string, checkEvery, repeatEvery time.Duration) {
	if reg == nil || checkEvery <= 0 {
		return
	}
	go func() {
		ticker := time.NewTicker(checkEvery)
		defer ticker.Stop()

		stateBySite := map[string]plcAlarmMonitorState{}
		checkPeriodicPLCAlarms(reg, mailSender, recipients, repeatEvery, stateBySite)
		for range ticker.C {
			checkPeriodicPLCAlarms(reg, mailSender, recipients, repeatEvery, stateBySite)
		}
	}()
}

func checkPeriodicPLCAlarms(reg systemservice.Registry, mailSender mail.Sender, recipients []string, repeatEvery time.Duration, stateBySite map[string]plcAlarmMonitorState) {
	now := time.Now().UTC()
	sites := reg.Sites()
	sort.Strings(sites)
	activeSites := make(map[string]struct{}, len(sites))

	for _, site := range sites {
		activeSites[site] = struct{}{}
		mgr, ok := reg.Get(site)
		if !ok || mgr == nil {
			continue
		}
		data, err := mgr.GetLatest()
		if err != nil {
			log.Printf("periodic plc-alarm check skipped for %s: GetLatest failed: %v", site, err)
			continue
		}
		ts, ok := latestTimestamp(data)
		if !ok {
			ts = now
		}
		ts = ts.UTC()

		alarmOn, alarmKey := evaluatePLCAlarmState(data)
		prev, hasPrev := stateBySite[site]
		if !hasPrev && runtimePLCAlarmStateStore != nil {
			stored, ok, err := runtimePLCAlarmStateStore.Get(context.Background(), site)
			if err != nil {
				log.Printf("periodic plc-alarm state load failed for %s: %v", site, err)
			} else if ok {
				prev = stored
				hasPrev = true
				stateBySite[site] = prev
			}
		}
		if !alarmOn {
			if prev.lastAlarmOn {
				log.Printf("plc alarm cleared for %s: last=%s", site, ts.Format(time.RFC3339))
			}
			prev.lastAlarmOn = false
			prev.lastAlarmKey = ""
			prev.lastSeenTS = ts
			prev.incidentResolvedAt = ts
			stateBySite[site] = prev
			if runtimePLCAlarmStateStore != nil && (hasPrev || prev.messageCount > 0) {
				if err := runtimePLCAlarmStateStore.Upsert(context.Background(), site, prev); err != nil {
					log.Printf("periodic plc-alarm state upsert failed for %s: %v", site, err)
				}
			}
			continue
		}

		shouldAlert := !prev.lastAlarmOn
		if !shouldAlert && prev.lastAlarmKey != alarmKey {
			shouldAlert = true
		}
		if !shouldAlert && repeatEvery > 0 && !prev.lastAlertAt.IsZero() && now.Sub(prev.lastAlertAt) >= repeatEvery {
			shouldAlert = true
		}
		if !shouldAlert && prev.lastSeenTS.Before(ts) {
			// Data advanced while still in alarm; update state but avoid extra alerts.
			prev.lastSeenTS = ts
			stateBySite[site] = prev
			if runtimePLCAlarmStateStore != nil {
				if err := runtimePLCAlarmStateStore.Upsert(context.Background(), site, prev); err != nil {
					log.Printf("periodic plc-alarm state upsert failed for %s: %v", site, err)
				}
			}
			continue
		}
		if !shouldAlert {
			prev.lastSeenTS = ts
			stateBySite[site] = prev
			if runtimePLCAlarmStateStore != nil {
				if err := runtimePLCAlarmStateStore.Upsert(context.Background(), site, prev); err != nil {
					log.Printf("periodic plc-alarm state upsert failed for %s: %v", site, err)
				}
			}
			continue
		}

		isRepeat := prev.lastAlarmOn && !prev.lastAlertAt.IsZero()
		sendPLCAlarmEmail(mailSender, recipients, site, ts, alarmKey, data, now, isRepeat, repeatEvery)
		next := prev
		if !prev.lastAlarmOn {
			next.incidentReportedAt = ts
			next.messageCount = 0
		}
		next.lastAlertAt = now
		next.lastSeenTS = ts
		next.lastAlarmOn = true
		next.lastAlarmKey = alarmKey
		next.messageCount++
		next.incidentResolvedAt = time.Time{}
		stateBySite[site] = next
		if runtimePLCAlarmStateStore != nil {
			if err := runtimePLCAlarmStateStore.Upsert(context.Background(), site, next); err != nil {
				log.Printf("periodic plc-alarm state upsert failed for %s: %v", site, err)
			}
		}
	}

	for site := range stateBySite {
		if _, ok := activeSites[site]; !ok {
			delete(stateBySite, site)
		}
	}
}

func evaluatePLCAlarmState(data map[string]interface{}) (bool, string) {
	if data == nil {
		return false, ""
	}
	if b, ok := toBoolAny(data["alarm"]); ok && b {
		return true, "alarm=1"
	}
	if w, ok := toIntAny(data["alarmword"]); ok && w != 0 {
		return true, fmt.Sprintf("alarmword=%d", w)
	}
	return false, ""
}

func sendPLCAlarmEmail(mailSender mail.Sender, recipients []string, site string, ts time.Time, alarmKey string, data map[string]interface{}, checkedAt time.Time, isRepeat bool, repeatEvery time.Duration) {
	subjectPrefix := "SVWaterGo PLC alarm alert"
	if isRepeat {
		subjectPrefix = "SVWaterGo PLC alarm reminder"
	}

	warn0, _ := toIntAny(data["warnword0"])
	warn1, _ := toIntAny(data["warnword1"])
	alarmWord, _ := toIntAny(data["alarmword"])
	body := strings.Builder{}
	body.WriteString("Admin!\n\n")
	body.WriteString(fmt.Sprintf("PLC alarm condition is active for %s.\n\n", formatSiteAlertName(site)))
	body.WriteString(fmt.Sprintf("Site key: %s\n", site))
	body.WriteString(fmt.Sprintf("Alarm condition: %s\n", alarmKey))
	body.WriteString(fmt.Sprintf("PLC Time (UTC): %s\n", ts.Format(time.RFC3339)))
	body.WriteString(fmt.Sprintf("Checked At (UTC): %s\n", checkedAt.Format(time.RFC3339)))
	body.WriteString(fmt.Sprintf("alarm=%v\n", data["alarm"]))
	body.WriteString(fmt.Sprintf("alarmword=%d\n", alarmWord))
	body.WriteString(fmt.Sprintf("warnword0=%d\n", warn0))
	body.WriteString(fmt.Sprintf("warnword1=%d\n", warn1))
	if repeatEvery > 0 {
		body.WriteString(fmt.Sprintf("\nAn automated reminder will be sent every %s while alarm remains active.\n", repeatEvery))
	}

	log.Printf("plc alarm alert for %s: %s ts=%s", site, alarmKey, ts.Format(time.RFC3339))
	if mailSender == nil || len(recipients) == 0 {
		return
	}
	if err := mailSender.Send(mail.Message{
		To:       recipients,
		Subject:  fmt.Sprintf("%s: %s", subjectPrefix, site),
		TextBody: body.String(),
		ReplyTo:  strings.Join(recipients, ", "),
	}); err != nil {
		log.Printf("plc alarm email failed for %s: %v", site, err)
	}
}

func formatSiteAlertName(site string) string {
	switch strings.ToLower(strings.TrimSpace(site)) {
	case "bluerock":
		return "Bluerock"
	case "santateresa":
		return "Santa Teresa"
	case "pryorfarm":
		return "Pryor Farms"
	default:
		if site == "" {
			return "Unknown"
		}
		return strings.TrimSpace(site)
	}
}

func latestTimestamp(data map[string]interface{}) (time.Time, bool) {
	if data == nil {
		return time.Time{}, false
	}
	for _, key := range []string{"plctime", "recordtime"} {
		raw, ok := data[key]
		if !ok || raw == nil {
			continue
		}
		switch v := raw.(type) {
		case time.Time:
			if v.IsZero() {
				return time.Time{}, false
			}
			return v, true
		case string:
			ts, err := time.Parse(time.RFC3339, strings.TrimSpace(v))
			if err == nil {
				return ts, true
			}
		}
	}
	return time.Time{}, false
}

func toBoolAny(v interface{}) (bool, bool) {
	switch t := v.(type) {
	case bool:
		return t, true
	case int:
		return t != 0, true
	case int64:
		return t != 0, true
	case int32:
		return t != 0, true
	case uint:
		return t != 0, true
	case uint64:
		return t != 0, true
	case uint32:
		return t != 0, true
	case float64:
		return t != 0, true
	case float32:
		return t != 0, true
	case string:
		s := strings.ToLower(strings.TrimSpace(t))
		switch s {
		case "1", "true", "yes", "on":
			return true, true
		case "0", "false", "no", "off", "":
			return false, true
		default:
			return false, false
		}
	default:
		return false, false
	}
}

func toIntAny(v interface{}) (int64, bool) {
	switch t := v.(type) {
	case int:
		return int64(t), true
	case int64:
		return t, true
	case int32:
		return int64(t), true
	case uint:
		return int64(t), true
	case uint64:
		return int64(t), true
	case uint32:
		return int64(t), true
	case float64:
		return int64(t), true
	case float32:
		return int64(t), true
	case string:
		s := strings.TrimSpace(t)
		if s == "" {
			return 0, false
		}
		n, err := strconv.ParseInt(s, 10, 64)
		if err != nil {
			return 0, false
		}
		return n, true
	default:
		return 0, false
	}
}

func envEnabled(name string) bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv(name)))
	switch v {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

func loadDBClientFromEnv() (*database.SQLXClient, error) {
	if pg := strings.TrimSpace(os.Getenv("DATABASE_URL")); pg != "" {
		log.Printf("Using Postgres backend from DATABASE_URL")
		return database.NewPostgresClient(pg)
	}
	path := strings.TrimSpace(os.Getenv("SQLITE_PATH"))
	if path == "" {
		path = "./data/svwatergo.db"
	}
	log.Printf("Using SQLite backend at %s", path)
	return database.NewSQLiteClient(path)
}
