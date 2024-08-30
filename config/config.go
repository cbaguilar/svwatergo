package config

import (
    "os"
    "log"
)

type Config struct {
    Port             string
    DBConnectionString string
    // Add other configuration fields as needed
}

// Load reads the configuration from environment variables
func Load() Config {
    config := Config{
        Port:             getEnv("APP_PORT", "8080"),
        DBConnectionString: getEnv("DB_CONNECTION_STRING", "user:password@/dbname"),
        // Load other fields as necessary
    }

    return config
}

// getEnv fetches the value of an environment variable or returns a default value if the variable is not set
func getEnv(key, defaultValue string) string {
    value, exists := os.LookupEnv(key)
    if !exists {
        value = defaultValue
    }
    return value
}
