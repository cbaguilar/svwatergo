package main

import (
	"github.com/cbaguilar/svwatergo/pkg/server"
)

var db = make(map[string]string)

func main() {

	server.New(&server.Config{
		Port: "8080",
	}).Start()

}
