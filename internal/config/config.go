package config

import (
	"os"
	"path/filepath"
	"strconv"
)

// Config holds runtime configuration options for dev-mcp.
type Config struct {
	WikiDir       string
	Host          string
	Port          int
	AuthToken     string
	WebhookSecret string
	SyncCron      string
	RepoURL       string
}

// LoadFromEnv loads default configuration overridden by environment variables.
func LoadFromEnv() *Config {
	cfg := &Config{
		WikiDir:       getEnv("WIKI_DIR", "."),
		Host:          getEnv("HOST", "0.0.0.0"),
		Port:          8080,
		AuthToken:     getEnv("AUTH_TOKEN", ""),
		WebhookSecret: getEnv("WEBHOOK_SECRET", ""),
		SyncCron:      getEnv("SYNC_CRON", ""),
		RepoURL:       getEnv("REPO_URL", ""),
	}

	if portStr := os.Getenv("PORT"); portStr != "" {
		if p, err := strconv.Atoi(portStr); err == nil {
			cfg.Port = p
		}
	}

	absDir, err := filepath.Abs(cfg.WikiDir)
	if err == nil {
		cfg.WikiDir = absDir
	}

	return cfg
}

func getEnv(key, fallback string) string {
	if val, ok := os.LookupEnv(key); ok && val != "" {
		return val
	}
	return fallback
}
