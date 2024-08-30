package server

import (
    "net/http"
    "log"
    "github.com/cbaguilar/svwatergo/internal/api"
    "github.com/cbaguilar/svwatergo/internal/sensor"
)

type Server struct {
    config        *Config
    sensorService sensor.Service
}

type Config struct {
    Port string
}

func New(cfg *Config, sensorService sensor.Service) *Server {
    return &Server{
        config:        cfg,
        sensorService: sensorService,
    }
}

func (s *Server) Start() error {
    mux := http.NewServeMux()
    api.RegisterRoutes(mux, s.sensorService)

    log.Printf("Server starting on port %s", s.config.Port)
    return http.ListenAndServe(":"+s.config.Port, mux)
}
