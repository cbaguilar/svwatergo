package config

import (
	"os"
	"strings"
)

type Config struct {
	Port        string
	DatabaseURL string
	SQLitePath  string

	MetadataDir    string
	AuthDisabled   bool
	IngestDisabled bool
	ReadOnlyMode   bool
}

// Load reads the configuration from environment variables
func Load() Config {
	return Config{
		Port:           getEnv("APP_PORT", "8080"),
		DatabaseURL:    strings.TrimSpace(os.Getenv("DATABASE_URL")),
		SQLitePath:     getEnv("SQLITE_PATH", "./data/svwatergo.db"),
		MetadataDir:    getEnv("SITE_METADATA_DIR", "config/sites"),
		AuthDisabled:   envEnabled("AUTH_DISABLED"),
		IngestDisabled: envEnabled("INGEST_DISABLED"),
		ReadOnlyMode:   envEnabled("READ_ONLY_MODE"),
	}.WithDefaults()
}

func (c Config) WithDefaults() Config {
	if strings.TrimSpace(c.Port) == "" {
		c.Port = "8080"
	}
	if strings.TrimSpace(c.SQLitePath) == "" {
		c.SQLitePath = "./data/svwatergo.db"
	}
	if strings.TrimSpace(c.MetadataDir) == "" {
		c.MetadataDir = "config/sites"
	}
	return c
}

// getEnv fetches the value of an environment variable or returns a default value if the variable is not set
func getEnv(key, defaultValue string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return defaultValue
	}
	return value
}

func envEnabled(name string) bool {
	switch strings.ToLower(strings.TrimSpace(os.Getenv(name))) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}
