package server

import (
	"context"
	"log"
	"os"
	"strings"

	"github.com/cbaguilar/svwatergo/config"
	"github.com/cbaguilar/svwatergo/internal/api"
	"github.com/cbaguilar/svwatergo/internal/auth"
	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/cbaguilar/svwatergo/internal/mail"
	"github.com/cbaguilar/svwatergo/internal/metadata"
	"github.com/cbaguilar/svwatergo/internal/reports"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/cbaguilar/svwatergo/internal/systemservice/bluerock"
	"github.com/cbaguilar/svwatergo/internal/systemservice/pryorfarm"
	"github.com/cbaguilar/svwatergo/internal/systemservice/santateresa"
)

type Server struct {
	config *Config
}

type Config struct {
	Port string
}

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

	var authn *auth.Auth
	adminEmails := auth.AdminEmailsFromEnv()
	if strings.TrimSpace(os.Getenv("AUTH_DISABLED")) == "" {
		authn = auth.MustNewFromEnv(context.Background())
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

	ingestDisabled := envEnabled("INGEST_DISABLED")
	readOnly := envEnabled("READ_ONLY_MODE")
	if readOnly {
		log.Printf("READ_ONLY_MODE enabled: mutating API routes are disabled")
	}
	if ingestDisabled {
		log.Printf("INGEST_DISABLED enabled: upload ingestion endpoints are disabled")
	}

	router := api.SetupRouter(ing, ing.Reg, metaStore, authn, reportsStore, mailSender, adminEmails, ingestDisabled, readOnly)
	log.Printf("Server starting on port %s", s.config.Port)
	return router.Run(":" + s.config.Port)
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
