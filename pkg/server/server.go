package server

import (
	"log"

	"github.com/cbaguilar/svwatergo/internal/api"
	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/cbaguilar/svwatergo/internal/systemservice/bluerock"
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

	digestionService := systemservice.DataIngestionService{
		Managers: map[string]systemservice.SystemManager{
			"bluerock": bluerock.NewBluerockManager(*sqliteDb),
		},
	}

	router := api.SetupRouter(&digestionService)
	log.Printf("Server starting on port %s", s.config.Port)
	return router.Run(":" + s.config.Port)
}
