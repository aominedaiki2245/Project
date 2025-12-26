package main

import "time"

// User — минимальные поля
type User struct {
    ID          string   `json:"id"`
    Email       string   `json:"email"`
    FullName    string   `json:"fullName"`
    Provider    string   `json:"provider"` // google/github/... optional
    ProviderID  string   `json:"providerId"`
    Roles       []string `json:"roles"`
    Permissions []string `json:"permissions"`
    CreatedAt   time.Time `json:"createdAt"`
}

// RefreshToken — хранится в БД для отзыва / refresh flow
type RefreshToken struct {
    Token     string
    UserID    string
    ExpiresAt time.Time
}
