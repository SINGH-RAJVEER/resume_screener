package auth

import (
	"errors"
	"log/slog"
	"net/http"
	"strings"
	"template/api/internal/database"
	apihttp "template/api/internal/http"
	"time"
)

type Config struct {
	JWTSecret string
	JWTTTL    time.Duration
}

type Handler struct {
	service service
}

func NewHandler(store Store, cfg Config) *Handler {
	return &Handler{
		service: service{store: store, jwtSecret: []byte(cfg.JWTSecret), jwtTTL: cfg.JWTTTL},
	}
}

func (h *Handler) SignUp(w http.ResponseWriter, r *http.Request) {
	var input signUpRequest
	if err := apihttp.DecodeJSON(r, &input); err != nil {
		apihttp.WriteError(w, http.StatusBadRequest, "INVALID_REQUEST", err.Error())
		return
	}

	result, err := h.service.register(r.Context(), input.Name, input.Email, input.Password)
	var invalid *validationError
	switch {
	case errors.As(err, &invalid):
		apihttp.WriteError(w, http.StatusBadRequest, "INVALID_CREDENTIALS", invalid.Error())
		return
	case errors.Is(err, database.ErrEmailUsed):
		apihttp.WriteError(w, http.StatusConflict, "EMAIL_ALREADY_EXISTS", "Email is already registered")
		return
	case err != nil:
		slog.Error("register user", "error", err)
		apihttp.WriteError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "Could not create account")
		return
	}

	apihttp.WriteJSON(w, http.StatusCreated, result)
}

func (h *Handler) SignIn(w http.ResponseWriter, r *http.Request) {
	var input signInRequest
	if err := apihttp.DecodeJSON(r, &input); err != nil {
		apihttp.WriteError(w, http.StatusBadRequest, "INVALID_REQUEST", err.Error())
		return
	}

	result, err := h.service.signIn(r.Context(), input.Email, input.Password)
	if errors.Is(err, ErrInvalidCredentials) {
		apihttp.WriteError(w, http.StatusUnauthorized, "INVALID_EMAIL_OR_PASSWORD", "Invalid email or password")
		return
	}
	if err != nil {
		slog.Error("sign in", "error", err)
		apihttp.WriteError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "Could not sign in")
		return
	}

	apihttp.WriteJSON(w, http.StatusOK, result)
}

func (h *Handler) SignOut(w http.ResponseWriter, _ *http.Request) {
	apihttp.WriteJSON(w, http.StatusOK, map[string]bool{"success": true})
}

func (h *Handler) GetSession(w http.ResponseWriter, r *http.Request) {
	user, ok := h.authenticatedUser(r)
	if !ok {
		apihttp.WriteJSON(w, http.StatusOK, nil)
		return
	}
	apihttp.WriteJSON(w, http.StatusOK, map[string]database.User{"user": user})
}

func (h *Handler) Me(w http.ResponseWriter, r *http.Request) {
	user, ok := h.authenticatedUser(r)
	if !ok {
		apihttp.WriteError(w, http.StatusUnauthorized, "UNAUTHORIZED", "Unauthorized")
		return
	}
	apihttp.WriteJSON(w, http.StatusOK, map[string]database.User{"user": user})
}

func (h *Handler) authenticatedUser(r *http.Request) (database.User, bool) {
	scheme, token, ok := strings.Cut(r.Header.Get("Authorization"), " ")
	if !ok || !strings.EqualFold(scheme, "Bearer") || token == "" {
		return database.User{}, false
	}
	user, err := h.service.authenticate(r.Context(), token)
	if err != nil {
		if !errors.Is(err, database.ErrNotFound) {
			slog.Debug("reject bearer token", "error", err)
		}
		return database.User{}, false
	}
	return user, true
}
