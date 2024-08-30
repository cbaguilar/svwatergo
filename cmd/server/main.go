package main

import (
    "log"
    "net/http"
    "github.com/cbaguilar/svwatergo/config"
    "github.com/cbaguilar/svwatergo/pkg/server"
    "github.com/cbaguilar/svwatergo/internal/database"
    "github.com/cbaguilar/svwatergo/internal/sensor"
)

func main() {
    cfg := config.Load()

    db, err := database.ConnectDB(cfg.DBConnectionString)
    if err != nil {
        log.Fatal("Could not connect to the database:", err)
    }

    sensorService := sensor.NewService(db)

    srv := server.New(cfg, sensorService)
    if err := srv.Start(); err != nil {
        log.Fatal("Failed to start server:", err)
    }
}