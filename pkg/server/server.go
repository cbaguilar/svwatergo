package server

import (
	"log"

	"github.com/cbaguilar/svwatergo/internal/api"
	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/cbaguilar/svwatergo/internal/metadata"
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

	// Here you would initialize and add your specific SystemManagers
	// e.g., ourIngestionService.Managers["bluerock"] = bluerock.NewBluerockManager(...)

	sqliteDb, err := database.NewSQLiteClient("./data/svwatergo.db")

	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}

	reg := systemservice.NewRegistry(map[string]systemservice.SystemManager{
		"bluerock":    bluerock.NewBluerockManager(*sqliteDb),
		"pryorfarm":   pryorfarm.NewPryorFarmManager(*sqliteDb),
		"santateresa": santateresa.NewSantaTeresaManager(*sqliteDb)})

	ing := &systemservice.DataIngestionService{
		Reg: reg,
	}

	metaStore, err := metadata.LoadDir("config/sites")
	if err != nil {
		log.Fatalf("Failed to load site metadata: %v", err)
	}

	router := api.SetupRouter(ing, ing.Reg, metaStore)
	log.Printf("Server starting on port %s", s.config.Port)
	return router.Run(":" + s.config.Port)
}
