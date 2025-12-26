package main

import (
    "context"
    "net/http"
    "strings"
)

type contextKey string

const ctxClaimsKey = contextKey("claims")

// VerifyMiddleware — проверяет Authorization: Bearer <token>, кладёт claims в контекст
func VerifyMiddleware(jm *JWTManager) func(http.Handler) http.Handler {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            h := r.Header.Get("Authorization")
            if h == "" || !strings.HasPrefix(h, "Bearer ") {
                http.Error(w, "unauthorized", http.StatusUnauthorized)
                return
            }
            token := strings.TrimPrefix(h, "Bearer ")
            claims, err := jm.VerifyToken(token)
            if err != nil {
                http.Error(w, "invalid token", http.StatusUnauthorized)
                return
            }
            ctx := context.WithValue(r.Context(), ctxClaimsKey, claims)
            next.ServeHTTP(w, r.WithContext(ctx))
        })
    }
}

// ExtractClaimsFromCtx helper
func ClaimsFromCtx(r *http.Request) *TokenClaims {
    v := r.Context().Value(ctxClaimsKey)
    if v == nil { return nil }
    if c, ok := v.(*TokenClaims); ok { return c }
    return nil
}
