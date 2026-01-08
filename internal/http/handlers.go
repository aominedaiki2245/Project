package auth

import (
	"net/http"
	"strings"

	"example.com/main-module/internal/auth"
)

func ProtectedHandler(w http.ResponseWriter, r *http.Request) {
	authHeader := r.Header.Get("Authorization")

	if !strings.HasPrefix(authHeader, "Bearer ") {
		w.WriteHeader(http.StatusUnauthorized)
		return
	}

	token := strings.TrimPrefix(authHeader, "Bearer ")

	ok, _ := auth.ValidateAccessToken(token)
	if !ok {
		w.WriteHeader(http.StatusUnauthorized)
		return
	}

	w.Write([]byte("Доступ разрешён"))
}