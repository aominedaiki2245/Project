package oauth

import (
	"auth-module/internal/notify"
	"encoding/json"
	"math/rand"
	"net/http"
	"strconv"
	"time"
)

type Handler struct {
	storage  *Storage
	telegram *notify.TelegramSender
}

func NewHandler(s *Storage, t *notify.TelegramSender) *Handler {
	return &Handler{
		storage:  s,
		telegram: t,
	}
}

func (h *Handler) SendCode(w http.ResponseWriter, r *http.Request) {
	identifier := r.URL.Query().Get("id")
	chatIDStr := r.URL.Query().Get("chat")

	chatID, err := strconv.ParseInt(chatIDStr, 10, 64)
	if err != nil || identifier == "" {
		http.Error(w, "Неверные параметры", http.StatusBadRequest)
		return
	}

	code := strconv.Itoa(rand.Intn(900000) + 100000)
	h.storage.SaveCode(identifier, code, 2*time.Minute)

	err = h.telegram.SendMessage(chatID, "Ваш код авторизации: "+code)
	if err != nil {
		http.Error(w, "Ошибка отправки кода", http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
	w.Write([]byte("Код отправлен"))
}

func (h *Handler) VerifyCode(w http.ResponseWriter, r *http.Request) {
	identifier := r.URL.Query().Get("id")
	code := r.URL.Query().Get("code")

	saved, ok := h.storage.GetCode(identifier)
	if !ok || saved != code {
		http.Error(w, "Неверный код", http.StatusUnauthorized)
		return
	}

	h.storage.DeleteCode(identifier)
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("Код подтверждён"))
}

func (h *Handler) GenerateToken(w http.ResponseWriter, r *http.Request) {
	identifier := r.URL.Query().Get("id")
	role := h.storage.GetUserRole(identifier)
	permissions := GetPermissionsForRole(role)

	token, refresh := GenerateTokens(identifier, permissions)
	h.storage.SaveRefreshToken(identifier, refresh, 24*time.Hour)

	json.NewEncoder(w).Encode(map[string]string{
		"access_token":  token,
		"refresh_token": refresh,
	})
}

func (h *Handler) RefreshToken(w http.ResponseWriter, r *http.Request) {
	refresh := r.URL.Query().Get("refresh")
	identifier, ok := h.storage.FindIdentifierByRefreshToken(refresh)
	if !ok {
		http.Error(w, "Неверный refresh токен", http.StatusUnauthorized)
		return
	}

	role := h.storage.GetUserRole(identifier)
	permissions := GetPermissionsForRole(role)

	token, newRefresh := GenerateTokens(identifier, permissions)
	h.storage.SaveRefreshToken(identifier, newRefresh, 24*time.Hour)

	json.NewEncoder(w).Encode(map[string]string{
		"access_token":  token,
		"refresh_token": newRefresh,
	})
}
