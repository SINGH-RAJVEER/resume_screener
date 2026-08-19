package auth

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"template/api/internal/database"
	apihttp "template/api/internal/http"
	"testing"
	"time"

	"golang.org/x/crypto/bcrypt"
)

type fakeStore struct {
	account      database.User
	passwordHash string
	registerErr  error
}

func (s *fakeStore) Register(_ context.Context, name, email, passwordHash string) (database.User, error) {
	if s.registerErr != nil {
		return database.User{}, s.registerErr
	}
	s.passwordHash = passwordHash
	s.account.Name = name
	s.account.Email = email
	return s.account, nil
}

func (s *fakeStore) Credentials(_ context.Context, email string) (database.User, string, error) {
	if email != s.account.Email {
		return database.User{}, "", database.ErrNotFound
	}
	return s.account, s.passwordHash, nil
}

func (s *fakeStore) User(_ context.Context, id string) (database.User, error) {
	if id != s.account.ID {
		return database.User{}, database.ErrNotFound
	}
	return s.account, nil
}

func testServer(store Store) http.Handler {
	handler := NewHandler(store, Config{JWTSecret: "test-secret-that-is-at-least-32-characters", JWTTTL: 24 * time.Hour})
	return apihttp.New(handler, "http://localhost:3000")
}

func TestHealth(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	response := httptest.NewRecorder()
	testServer(&fakeStore{}).ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", response.Code)
	}
	if strings.TrimSpace(response.Body.String()) != `{"status":"ok"}` {
		t.Fatalf("unexpected response: %s", response.Body.String())
	}
}

func TestSignUpReturnsJWT(t *testing.T) {
	store := &fakeStore{
		account: database.User{ID: "user-1"},
	}
	request := httptest.NewRequest(http.MethodPost, "/api/auth/sign-up/email", bytes.NewBufferString(`{"name":"Ada","email":"ADA@example.com","password":"password123"}`))
	response := httptest.NewRecorder()
	testServer(store).ServeHTTP(response, request)

	if response.Code != http.StatusCreated {
		t.Fatalf("expected status 201, got %d: %s", response.Code, response.Body.String())
	}
	if store.account.Email != "ada@example.com" {
		t.Fatalf("expected normalized email, got %q", store.account.Email)
	}
	if bcrypt.CompareHashAndPassword([]byte(store.passwordHash), []byte("password123")) != nil {
		t.Fatal("password was not stored as a bcrypt hash")
	}
	var payload authResponse
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
		t.Fatal(err)
	}
	if payload.Token == "" || payload.TokenType != "Bearer" {
		t.Fatalf("expected bearer JWT, got %#v", payload)
	}
}

func TestSignUpRejectsTrailingJSON(t *testing.T) {
	request := httptest.NewRequest(http.MethodPost, "/api/auth/sign-up/email", bytes.NewBufferString(`{"name":"Ada","email":"ada@example.com","password":"password123"} {}`))
	response := httptest.NewRecorder()
	testServer(&fakeStore{}).ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", response.Code)
	}
}

func TestSignInRejectsInvalidPassword(t *testing.T) {
	passwordHash, err := bcrypt.GenerateFromPassword([]byte("correct-password"), bcrypt.MinCost)
	if err != nil {
		t.Fatal(err)
	}
	store := &fakeStore{account: database.User{ID: "user-1", Email: "ada@example.com"}, passwordHash: string(passwordHash)}
	request := httptest.NewRequest(http.MethodPost, "/api/auth/sign-in/email", bytes.NewBufferString(`{"email":"ada@example.com","password":"wrong-password"}`))
	response := httptest.NewRecorder()
	testServer(store).ServeHTTP(response, request)
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("expected status 401, got %d", response.Code)
	}
}

func TestMeRequiresValidJWT(t *testing.T) {
	store := &fakeStore{account: database.User{ID: "user-1", Name: "Ada"}}
	result, err := (&service{store: store, jwtSecret: []byte("test-secret-that-is-at-least-32-characters"), jwtTTL: time.Hour}).issueToken(store.account)
	if err != nil {
		t.Fatal(err)
	}

	unauthorizedRequest := httptest.NewRequest(http.MethodGet, "/api/me", nil)
	unauthorizedResponse := httptest.NewRecorder()
	testServer(store).ServeHTTP(unauthorizedResponse, unauthorizedRequest)
	if unauthorizedResponse.Code != http.StatusUnauthorized {
		t.Fatalf("expected missing bearer token to return 401, got %d", unauthorizedResponse.Code)
	}

	authorizedRequest := httptest.NewRequest(http.MethodGet, "/api/me", nil)
	authorizedRequest.Header.Set("Authorization", "Bearer "+result.Token)
	authorizedResponse := httptest.NewRecorder()
	testServer(store).ServeHTTP(authorizedResponse, authorizedRequest)
	if authorizedResponse.Code != http.StatusOK {
		t.Fatalf("expected valid JWT to return 200, got %d", authorizedResponse.Code)
	}
	var payload struct {
		User database.User `json:"user"`
	}
	if err := json.NewDecoder(authorizedResponse.Body).Decode(&payload); err != nil {
		t.Fatal(err)
	}
	if payload.User.ID != store.account.ID {
		t.Fatalf("expected user %q, got %q", store.account.ID, payload.User.ID)
	}
}

func TestMeRejectsExpiredJWT(t *testing.T) {
	store := &fakeStore{account: database.User{ID: "user-1"}}
	result, err := (&service{store: store, jwtSecret: []byte("test-secret-that-is-at-least-32-characters"), jwtTTL: -time.Hour}).issueToken(store.account)
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodGet, "/api/me", nil)
	request.Header.Set("Authorization", "Bearer "+result.Token)
	response := httptest.NewRecorder()
	testServer(store).ServeHTTP(response, request)
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("expected expired JWT to return 401, got %d", response.Code)
	}
}

func TestSignOutSucceeds(t *testing.T) {
	store := &fakeStore{}
	request := httptest.NewRequest(http.MethodPost, "/api/auth/sign-out", nil)
	response := httptest.NewRecorder()
	testServer(store).ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", response.Code)
	}
	if strings.TrimSpace(response.Body.String()) != `{"success":true}` {
		t.Fatalf("unexpected response: %s", response.Body.String())
	}
}

func TestCORS(t *testing.T) {
	server := testServer(&fakeStore{})
	allowedRequest := httptest.NewRequest(http.MethodOptions, "/api/auth/session", nil)
	allowedRequest.Header.Set("Origin", "http://localhost:3000")
	allowedResponse := httptest.NewRecorder()
	server.ServeHTTP(allowedResponse, allowedRequest)
	if allowedResponse.Code != http.StatusNoContent {
		t.Fatalf("expected preflight status 204, got %d", allowedResponse.Code)
	}
	if !strings.Contains(allowedResponse.Header().Get("Access-Control-Allow-Headers"), "Authorization") {
		t.Fatal("expected Authorization to be allowed by CORS")
	}

	blockedRequest := httptest.NewRequest(http.MethodGet, "/health", nil)
	blockedRequest.Header.Set("Origin", "https://attacker.example")
	blockedResponse := httptest.NewRecorder()
	server.ServeHTTP(blockedResponse, blockedRequest)
	if blockedResponse.Code != http.StatusForbidden {
		t.Fatalf("expected untrusted origin status 403, got %d", blockedResponse.Code)
	}
}

func TestEmailConflict(t *testing.T) {
	store := &fakeStore{registerErr: database.ErrEmailUsed}
	request := httptest.NewRequest(http.MethodPost, "/api/auth/sign-up/email", bytes.NewBufferString(`{"name":"Ada","email":"ada@example.com","password":"password123"}`))
	response := httptest.NewRecorder()
	testServer(store).ServeHTTP(response, request)
	if response.Code != http.StatusConflict {
		t.Fatalf("expected status 409, got %d", response.Code)
	}
}

var _ Store = (*fakeStore)(nil)
