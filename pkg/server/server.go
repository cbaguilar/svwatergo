package server

import (
	"log"

	"github.com/cbaguilar/svwatergo/internal/api"
	"github.com/gin-gonic/gin"
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
	router := gin.Default()
	api.SetupRouter()

	log.Printf("Server starting on port %s", s.config.Port)
	return router.Run(":" + s.config.Port)
}
