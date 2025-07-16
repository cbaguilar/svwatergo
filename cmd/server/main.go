package main

import (
	"github.com/cbaguilar/svwatergo/internal/api" // Adjust the import path according to your project structure
)

var db = make(map[string]string)

func main() {

	r := api.SetupRouter() // Call the setupRouter function from the imported package
	// Listen and Server in 0.0.0.0:8080
	r.Run(":8080")
}
