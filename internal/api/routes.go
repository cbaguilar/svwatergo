package api

import (
    "net/http"
    "github.com/cbaguilar/svwatergo/internal/sensor"
)

func RegisterRoutes(mux *http.ServeMux, service sensor.Service) {
    mux.HandleFunc("/sensor", SaveSensorDataHandler(service))
}

/* v0 routes, re-implemented for backwards compatibility before we add
   better-desigend routes. */
