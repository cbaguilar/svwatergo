package api

import (
    "net/http"
    "github.com/cbaguilar/svwatergo/internal/sensor"
)

func RegisterRoutes(mux *http.ServeMux, service sensor.Service) {
    mux.HandleFunc("/sensor", SaveSensorDataHandler(service))
}
