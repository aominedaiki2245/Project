package main

import (
    "context"
    "crypto/rand"
    "encoding/base64"
    "fmt"
    "net/http"

    "golang.org/x/oauth2"
    "golang.org/x/oauth2/github"
    "golang.org/x/oauth2/google"
)

// Поддерживаемые провайдеры
type OAuthProvider string

const (
    ProviderGoogle OAuthProvider = "google"
    ProviderGitHub OAuthProvider = "github"
)

type OAuthManager struct {
    googleConf *oauth2.Config
    ghConf     *oauth2.Config
    baseURL    string // callback base url, like https://auth.mydomain
}

func NewOAuthManager(baseURL, googleID, googleSecret, ghID, ghSecret, redirectPath string) *OAuthManager {
    redirect := fmt.Sprintf("%s%s", baseURL, redirectPath) // e.g. /oauth/callback
    googleConf := &oauth2.Config{
        ClientID: googleID,
        ClientSecret: googleSecret,
        Endpoint: google.Endpoint,
        RedirectURL: redirect,
        Scopes: []string{"openid", "email", "profile"},
    }
    ghConf := &oauth2.Config{
        ClientID: ghID,
        ClientSecret: ghSecret,
        Endpoint: github.Endpoint,
        RedirectURL: redirect,
        Scopes: []string{"user:email"},
    }
    return &OAuthManager{
        googleConf: googleConf, ghConf: ghConf, baseURL: baseURL,
    }
}

func (o *OAuthManager) StateToken() (string, error) {
    b := make([]byte, 32)
    _, err := rand.Read(b)
    if err != nil { return "", err }
    return base64.RawURLEncoding.EncodeToString(b), nil
}

func (o *OAuthManager) AuthURL(provider OAuthProvider, state string) string {
    switch provider {
    case ProviderGoogle:
        return o.googleConf.AuthCodeURL(state, oauth2.AccessTypeOffline)
    case ProviderGitHub:
        return o.ghConf.AuthCodeURL(state, oauth2.AccessTypeOffline)
    default:
        return ""
    }
}

func (o *OAuthManager) Exchange(ctx context.Context, provider OAuthProvider, code string) (*oauth2.Token, error) {
    switch provider {
    case ProviderGoogle:
        return o.googleConf.Exchange(ctx, code)
    case ProviderGitHub:
        return o.ghConf.Exchange(ctx, code)
    default:
        return nil, fmt.Errorf("unknown provider")
    }
}
