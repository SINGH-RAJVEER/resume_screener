package config

import (
	"fmt"
	"os"
	"time"
)

type Config struct {
	DatabaseURL string
	Port        string
	WebURL      string
	JWTSecret   string
	JWTTTL      time.Duration
}

func Load() (Config, error) {
	cfg := Config{
		DatabaseURL: os.Getenv("DATABASE_URL"),
		Port:        envOrDefault("PORT", "3001"),
		WebURL:      envOrDefault("WEB_URL", "http://localhost:3000"),
		JWTSecret:   os.Getenv("JWT_SECRET"),
		JWTTTL:      7 * 24 * time.Hour,
	}

	if cfg.DatabaseURL == "" {
		return Config{}, fmt.Errorf("DATABASE_URL environment variable is required")
	}
	if len(cfg.JWTSecret) < 32 {
		return Config{}, fmt.Errorf("JWT_SECRET environment variable must be at least 32 characters")
	}

	if value := os.Getenv("JWT_TTL"); value != "" {
		ttl, err := time.ParseDuration(value)
		if err != nil || ttl <= 0 {
			return Config{}, fmt.Errorf("JWT_TTL must be a positive duration")
		}
		cfg.JWTTTL = ttl
	}

	return cfg, nil
}
func envOrDefault(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}
