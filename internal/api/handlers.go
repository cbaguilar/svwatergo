package api

import (
    "net/http"
    "encoding/json"
    "github.com/cbaguilar/svwatergo/internal/sensor"
)

func SaveSensorDataHandler(service sensor.Service) http.HandlerFunc {
    return func(w http.ResponseWriter, r *http.Request) {
        if r.Method != http.MethodPost {
            http.Error(w, "Invalid request method", http.StatusMethodNotAllowed)
            return
        }

        var data sensor.SensorData
        if err := json.NewDecoder(r.Body).Decode(&data); err != nil {
            http.Error(w, "Invalid request", http.StatusBadRequest)
            return
        }

        if err := service.SaveSensorData(data); err != nil {
            http.Error(w, "Could not save data", http.StatusInternalServerError)
            return
        }

        w.WriteHeader(http.StatusCreated)
    }
}
