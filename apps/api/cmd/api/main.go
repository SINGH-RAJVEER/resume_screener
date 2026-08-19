package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"template/api/internal/auth"
	"template/api/internal/config"
	"template/api/internal/database"
	apihttp "template/api/internal/http"
	"time"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		slog.Error("load configuration", "error", err)
		os.Exit(1)
	}

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	store, err := database.Open(ctx, cfg.DatabaseURL)
	if err != nil {
		slog.Error("initialize store", "error", err)
		os.Exit(1)
	}
	defer store.Close()

	authHandler := auth.NewHandler(store, auth.Config{
		JWTSecret: cfg.JWTSecret,
		JWTTTL:    cfg.JWTTTL,
	})
	server := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           apihttp.New(authHandler, cfg.WebURL),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	go func() {
		slog.Info("server started", "port", cfg.Port)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("serve HTTP", "error", err)
			cancel()
		}
	}()

	<-ctx.Done()
	shutdownContext, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()
	if err := server.Shutdown(shutdownContext); err != nil {
		slog.Error("shutdown server", "error", err)
	}
}
