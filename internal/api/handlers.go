package api

import (
    "net/http"
    "encoding/json"
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


// Helper function to parse the media type from the Content-Type header
func parseMediaType(contentType string) string {
	for i := 0; i < len(contentType); i++ {
		if contentType[i] == ';' {
			return contentType[:i]
		}
	}
	return contentType
}

type UploadDataV0Request {
	
}

func UploadDataV0() http.HandlerFunc {
	/* Data can be zipped or unzipped, so we have to handle this differently */


	return func(w, http.ResponseWriter, r *http.Request) {

		if r.Method != http.MethodPost {
			http.Error(w, "Invalid request method", http.StatusMethodNotAllowed)
            return
		}

		contentType := parseMediaType(r.Header.Get("Content-Type"))
		
		if contentType == "application/zip" {
			//unzip the data...
			//TODO: Unzip data
		}
		
	}
}
