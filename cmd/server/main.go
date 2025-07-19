package main

import (
	"github.com/cbaguilar/svwatergo/internal/api" // Adjust the import path according to your project structure
	"github.com/cbaguilar/svwatergo/internal/system_contract"
	systemservice "github.com/cbaguilar/svwatergo/internal/system_service"
	"github.com/cbaguilar/svwatergo/internal/system_service/bluerock"
)

var db = make(map[string]string)

func main() {

	ingestionService := &systemservice.DataIngestionService{
		Managers: map[string]system_contract.SystemManager{
			"Bluerock": &bluerock.BluerockManager{},
		},
	}
	r := api.SetupRouter(ingestionService) // Call the setupRouter function from the imported package
	// Listen and Server in 0.0.0.0:8080

	r.Run(":8080")
}
