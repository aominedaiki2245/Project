package main

import (
    "fmt"
    "log"
    "net/http"
    "os"
    "strconv"

    "github.com/go-chi/chi/v5"
)

func main() {
    // load env config (simplified)
    privKey := os.Getenv("PRIVATE_KEY_PATH"); if privKey == "" { privKey = "./keys/private.key.pem" }
    pubKey := os.Getenv("PUBLIC_KEY_PATH"); if pubKey == "" { pubKey = "./keys/public.key.pem" }
    issuer := envOr("JWT_ISSUER", "auth.example")
    audience := envOr("JWT_AUDIENCE", "main-service")
    expMinutesStr := envOr("JWT_EXPIRE_MINUTES", "60")
    expMinutes, _ := strconv.Atoi(expMinutesStr)

    jwtm, err := NewJWTManager(privKey, pubKey, issuer, audience, expMinutes)
    if err != nil { log.Fatalf("jwt init: %v", err) }

    baseURL := envOr("BASE_URL", "http://localhost:8081")
    // example: get google/github client ids from env
    oauthm := NewOAuthManager(baseURL, os.Getenv("OAUTH_GOOGLE_CLIENT_ID"), os.Getenv("OAUTH_GOOGLE_CLIENT_SECRET"),
        os.Getenv("OAUTH_GITHUB_CLIENT_ID"), os.Getenv("OAUTH_GITHUB_CLIENT_SECRET"), "/oauth/callback")

    repo := NewInMemoryRepo()

    s := &Server{repo: repo, jwtm: jwtm, oauth: oauthm, baseURL: baseURL, refreshTTLDays: 30}

    r := chi.NewRouter()

    r.Get("/health", func(w http.ResponseWriter, r *http.Request){ w.Write([]byte("OK")) })

    // OAuth endpoints
    r.Get("/oauth/start/{provider}", s.OAuthStart)
    // providers should send provider param to callback or state encoding in prod
    r.Get("/oauth/callback", s.OAuthCallback)

    // token refresh
    r.Post("/token/refresh", s.RefreshToken)

    // verify used by main module
    r.Get("/verify", s.VerifyHandler)

    // jwks
    r.Get("/.well-known/jwks.json", func(w http.ResponseWriter, r *http.Request){
        b, _ := jwtm.JwksJSON()
        w.Header().Set("Content-Type", "application/json")
        w.Write(b)
    })

    // admin actions
    adminR := chi.NewRouter()
    adminR.Use(VerifyMiddleware(jwtm))
    adminR.Post("/assign-role", s.AssignRoleHandler)
    r.Mount("/admin", adminR)

    port := envOr("AUTH_PORT", "8081")
    fmt.Printf("Auth module starting on :%s\n", port)
    http.ListenAndServe(":"+port, r)
}

func envOr(k, def string) string {
    v := os.Getenv(k)
    if v == "" { return def }
    return v
}
