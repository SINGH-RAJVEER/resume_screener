package auth

import (
	"context"
	"errors"
	"fmt"
	"net/mail"
	"strings"
	"template/api/internal/database"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"golang.org/x/crypto/bcrypt"
)

var ErrInvalidCredentials = errors.New("invalid email or password")

type service struct {
	store     Store
	jwtSecret []byte
	jwtTTL    time.Duration
}

func (s *service) register(ctx context.Context, name, email, password string) (authResponse, error) {
	name = strings.TrimSpace(name)
	email = strings.ToLower(strings.TrimSpace(email))
	if message := validateCredentials(name, email, password); message != "" {
		return authResponse{}, &validationError{message: message}
	}

	passwordHash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return authResponse{}, err
	}
	user, err := s.store.Register(ctx, name, email, string(passwordHash))
	if err != nil {
		return authResponse{}, err
	}
	return s.issueToken(user)
}

func (s *service) signIn(ctx context.Context, email, password string) (authResponse, error) {
	email = strings.ToLower(strings.TrimSpace(email))
	account, passwordHash, err := s.store.Credentials(ctx, email)
	if err != nil || bcrypt.CompareHashAndPassword([]byte(passwordHash), []byte(password)) != nil {
		return authResponse{}, ErrInvalidCredentials
	}
	return s.issueToken(account)
}

func (s *service) issueToken(user database.User) (authResponse, error) {
	now := time.Now().UTC()
	expiresAt := now.Add(s.jwtTTL)
	claims := jwt.RegisteredClaims{
		Issuer:    "template-api",
		Subject:   user.ID,
		IssuedAt:  jwt.NewNumericDate(now),
		ExpiresAt: jwt.NewNumericDate(expiresAt),
	}
	token, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString(s.jwtSecret)
	if err != nil {
		return authResponse{}, fmt.Errorf("sign JWT: %w", err)
	}
	return authResponse{User: user, Token: token, TokenType: "Bearer", ExpiresAt: expiresAt}, nil
}

func (s *service) authenticate(ctx context.Context, token string) (database.User, error) {
	claims := new(jwt.RegisteredClaims)
	parsed, err := jwt.ParseWithClaims(token, claims, func(token *jwt.Token) (any, error) {
		if token.Method != jwt.SigningMethodHS256 {
			return nil, fmt.Errorf("unexpected signing method")
		}
		return s.jwtSecret, nil
	}, jwt.WithIssuer("template-api"), jwt.WithExpirationRequired())
	if err != nil || !parsed.Valid || claims.Subject == "" {
		return database.User{}, ErrInvalidCredentials
	}
	return s.store.User(ctx, claims.Subject)
}

func validateCredentials(name, email, password string) string {
	if name == "" || len(name) > 100 {
		return "Name must be between 1 and 100 characters"
	}
	address, err := mail.ParseAddress(email)
	if err != nil || !strings.EqualFold(address.Address, email) || len(email) > 254 {
		return "Enter a valid email address"
	}
	if len(password) < 8 || len(password) > 72 {
		return "Password must be between 8 and 72 characters"
	}
	return ""
}

type validationError struct {
	message string
}

func (e *validationError) Error() string {
	return e.message
}
