package main

import (
	"fmt"
	"log"
	"net/http"
	"time"

	"auth-module/internal/notify"
	"auth-module/internal/oauth"
)

func main() {

	storage := oauth.NewStorage()
	telegram := &notify.TelegramSender{
		BotToken: "ТОКЕН_БОТА",
	}

	handler := oauth.NewHandler(storage, telegram)

	go func() {
		ticker := time.NewTicker(1 * time.Minute)
		for range ticker.C {
			storage.CleanupExpiredRefreshTokens()
			storage.CleanupExpiredCodes()
			storage.CleanupExpiredAttempts()
		}
	}()

	mux := http.NewServeMux()

	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, "Модуль авторизации работает")
	})

	mux.HandleFunc("/oauth/code", handler.SendCode)
	mux.HandleFunc("/oauth/verify", handler.VerifyCode)
	mux.HandleFunc("/oauth/token", handler.GenerateToken)
	mux.HandleFunc("/oauth/refresh", handler.RefreshToken)

	mux.Handle("/profile", oauth.AuthMiddleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("Это защищённый профиль"))
	})))

	log.Println("Сервер запущен на :8080")
	if err := http.ListenAndServe(":8080", mux); err != nil {
		log.Fatalf("Ошибка запуска сервера: %v", err)
	}
}

