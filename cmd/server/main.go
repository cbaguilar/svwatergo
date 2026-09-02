package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/cbaguilar/svwatergo/config"
	"github.com/cbaguilar/svwatergo/pkg/server"
)

func main() {
	if err := config.LoadDotEnv(".env"); err != nil {
		log.Printf("Failed to load .env: %v", err)
	}
	cfg := config.Load()
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := server.New(&cfg).StartContext(ctx); err != nil {
		log.Printf("server stopped: %v", err)
		os.Exit(1)
	}
}
