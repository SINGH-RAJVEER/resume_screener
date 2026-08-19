package http

import "net/http"

type AuthHandler interface {
	SignUp(http.ResponseWriter, *http.Request)
	SignIn(http.ResponseWriter, *http.Request)
	SignOut(http.ResponseWriter, *http.Request)
	GetSession(http.ResponseWriter, *http.Request)
	Me(http.ResponseWriter, *http.Request)
}

func New(auth AuthHandler, webURL string) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", health)
	mux.HandleFunc("POST /api/auth/sign-up/email", auth.SignUp)
	mux.HandleFunc("POST /api/auth/sign-in/email", auth.SignIn)
	mux.HandleFunc("POST /api/auth/sign-out", auth.SignOut)
	mux.HandleFunc("GET /api/auth/session", auth.GetSession)
	mux.HandleFunc("GET /api/me", auth.Me)
	return middleware(mux, webURL)
}

func health(w http.ResponseWriter, _ *http.Request) {
	WriteJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}
