package main

import (
	"os"
	"strings"

	"github.com/cbaguilar/svwatergo/pkg/server"
)

var db = make(map[string]string)

func main() {
	port := strings.TrimSpace(os.Getenv("APP_PORT"))
	if port == "" {
		port = "8080"
	}

	server.New(&server.Config{
		Port: port,
	}).Start()

}
