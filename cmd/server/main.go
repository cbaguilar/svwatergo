package main

import (
	"github.com/cbaguilar/svwatergo/internal/api" // Adjust the import path according to your project structure
)

var db = make(map[string]string)

func main() {

	// We inject a sensor service into the router,
	// so we can test the sensor service in isolation.

	sensorService := sensor.NewSensorService(db)
	r := api.SetupRouter() // Call the setupRouter function from the imported package
	// Listen and Server in 0.0.0.0:8080
	r.Run(":8080")
}
