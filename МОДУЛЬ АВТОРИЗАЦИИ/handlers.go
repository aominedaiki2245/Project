package main

import (
    "context"
    "crypto/rand"
    "encoding/base64"
    "encoding/json"
    "fmt"
    "net/http"
    "time"

    "github.com/go-chi/chi/v5"
)

// generateID simple
func generateID(prefix string) string {
    b := make([]byte, 8)
    rand.Read(b)
    return fmt.Sprintf("%s_%s", prefix, base64.RawURLEncoding.EncodeToString(b))
}

type Server struct {
    repo   Repo
    jwtm   *JWTManager
    oauth  *OAuthManager
    baseURL string
    refreshTTLDays int
}

// Start OAuth flow: redirect to provider
func (s *Server) OAuthStart(w http.ResponseWriter, r *http.Request) {
    provider := chi.URLParam(r, "provider")
    state, _ := s.oauth.StateToken()
    // In prod: save state in DB or signed cookie to prevent CSRF
    url := s.oauth.AuthURL(OAuthProvider(provider), state)
    http.Redirect(w, r, url, http.StatusFound)
}

// OAuth callback: exchange code -> get user info -> create or find user -> issue tokens
func (s *Server) OAuthCallback(w http.ResponseWriter, r *http.Request) {
    ctx := r.Context()
    code := r.URL.Query().Get("code")
    state := r.URL.Query().Get("state")
    provider := r.URL.Query().Get("provider") // optionally passed via state/param
    if code == "" {
        http.Error(w, "code missing", http.StatusBadRequest); return
    }
    // Exchange
    token, err := s.oauth.Exchange(ctx, OAuthProvider(provider), code)
    if err != nil { http.Error(w, "exchange failed: "+err.Error(), http.StatusInternalServerError); return }
    // Get userinfo — for brevity we skip provider-specific userinfo fetch and simulate
    // In production: fetch email/subject from provider's userinfo endpoint.
    providerID := token.AccessToken[:10] // placeholder — replace with real ID/email
    email := fmt.Sprintf("%s@%s.example", providerID, provider)
    // find or create user
    u, err := s.repo.GetUserByProvider(ctx, provider, providerID)
    if err != nil {
        // create
        u = &User{
            ID: generateID("u"),
            Email: email,
            FullName: "OAuth User",
            Provider: provider,
            ProviderID: providerID,
            Roles: []string{"Student"}, // default role
            Permissions: []string{},
            CreatedAt: time.Now().UTC(),
        }
        _ = s.repo.CreateUser(ctx, u)
    }
    // Generate JWT + refresh token
    jwtStr, exp, err := s.jwtm.GenerateToken(u)
    if err != nil { http.Error(w, "jwt gen failed", http.StatusInternalServerError); return }
    refresh := generateID("rt")
    rt := &RefreshToken{Token: refresh, UserID: u.ID, ExpiresAt: time.Now().Add(time.Duration(s.refreshTTLDays) * 24 * time.Hour)}
    _ = s.repo.SaveRefreshToken(ctx, rt)
    // respond JSON (for browser-based flow set secure HttpOnly cookie instead)
    resp := map[string]interface{}{"access_token": jwtStr, "expires_at": exp.Unix(), "refresh_token": refresh, "user": u}
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(resp)
}

// Token refresh endpoint
func (s *Server) RefreshToken(w http.ResponseWriter, r *http.Request) {
    ctx := r.Context()
    var body struct { RefreshToken string `json:"refresh_token"` }
    if err := json.NewDecoder(r.Body).Decode(&body); err != nil { http.Error(w, "bad body", http.StatusBadRequest); return }
    rt, err := s.repo.GetRefreshToken(ctx, body.RefreshToken)
    if err != nil { http.Error(w, "invalid refresh", http.StatusUnauthorized); return }
    u, err := s.repo.GetUserByID(ctx, rt.UserID)
    if err != nil { http.Error(w, "user not found", http.StatusUnauthorized); return }
    tok, exp, err := s.jwtm.GenerateToken(u)
    if err != nil { http.Error(w, "jwt create error", http.StatusInternalServerError); return }
    // rotate refresh token
    newRT := generateID("rt")
    s.repo.DeleteRefreshToken(ctx, body.RefreshToken)
    _ = s.repo.SaveRefreshToken(ctx, &RefreshToken{Token: newRT, UserID: u.ID, ExpiresAt: time.Now().Add(time.Duration(s.refreshTTLDays) * 24 * time.Hour)})
    json.NewEncoder(w).Encode(map[string]interface{}{"access_token": tok, "expires_at": exp.Unix(), "refresh_token": newRT})
}

// Verify endpoint used by main module
func (s *Server) VerifyHandler(w http.ResponseWriter, r *http.Request) {
    // Accept Authorization header
    auth := r.Header.Get("Authorization")
    if auth == "" { http.Error(w, "no auth", http.StatusUnauthorized); return }
    if len(auth) < 7 || auth[:7] != "Bearer " { http.Error(w, "invalid auth header", http.StatusUnauthorized); return }
    token := auth[7:]
    claims, err := s.jwtm.VerifyToken(token)
    if err != nil { http.Error(w, "invalid token", http.StatusUnauthorized); return }
    // Build response matching what main module expects
    resp := map[string]interface{}{
        "userId": claims.UserID,
        "roles": claims.Roles,
        "permissions": claims.Permissions,
        "exp": claims.ExpiresAt.Unix(),
    }
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(resp)
}

// Admin endpoints: protect with VerifyMiddleware + admin role check
func (s *Server) AssignRoleHandler(w http.ResponseWriter, r *http.Request) {
    // require admin role
    claims := ClaimsFromCtx(r)
    if claims == nil { http.Error(w, "unauth", http.StatusUnauthorized); return }
    hasAdmin := false
    for _, rr := range claims.Roles { if rr == "Admin" { hasAdmin = true } }
    if !hasAdmin { http.Error(w, "forbidden", http.StatusForbidden); return }

    var body struct{ UserID string `json:"userId"`; Role string `json:"role"` }
    if err := json.NewDecoder(r.Body).Decode(&body); err != nil { http.Error(w, "bad body", http.StatusBadRequest); return }
    if err := s.repo.AssignRole(r.Context(), body.UserID, body.Role); err != nil { http.Error(w, "assign error", http.StatusInternalServerError); return }
    w.WriteHeader(http.StatusOK)
}
