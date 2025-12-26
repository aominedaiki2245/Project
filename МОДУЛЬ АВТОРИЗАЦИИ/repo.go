package main

import "context"

type Repo interface {
    // User
    CreateUser(ctx context.Context, u *User) error
    GetUserByID(ctx context.Context, id string) (*User, error)
    GetUserByProvider(ctx context.Context, provider, providerID string) (*User, error)
    UpdateUser(ctx context.Context, u *User) error

    // Roles/permissions management
    AssignRole(ctx context.Context, userID, role string) error
    RemoveRole(ctx context.Context, userID, role string) error
    SetPermissions(ctx context.Context, userID string, perms []string) error

    // Refresh tokens
    SaveRefreshToken(ctx context.Context, rt *RefreshToken) error
    GetRefreshToken(ctx context.Context, token string) (*RefreshToken, error)
    DeleteRefreshToken(ctx context.Context, token string) error
}
