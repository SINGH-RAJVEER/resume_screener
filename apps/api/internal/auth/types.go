package auth

import (
	"template/api/internal/database"
	"time"
)

type signUpRequest struct {
	Name        string `json:"name"`
	Email       string `json:"email"`
	Password    string `json:"password"`
	CallbackURL string `json:"callbackURL"`
}

type signInRequest struct {
	Email       string `json:"email"`
	Password    string `json:"password"`
	CallbackURL string `json:"callbackURL"`
}

type authResponse struct {
	User      database.User `json:"user"`
	Token     string        `json:"token"`
	TokenType string        `json:"tokenType"`
	ExpiresAt time.Time     `json:"expiresAt"`
}
