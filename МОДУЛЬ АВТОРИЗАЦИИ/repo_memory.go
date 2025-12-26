package main

import (
    "context"
    "errors"
    "sync"
    "time"
)

var ErrNotFound = errors.New("not found")

type InMemoryRepo struct {
    users map[string]*User
    rmap  map[string]*RefreshToken
    mu    sync.RWMutex
}

func NewInMemoryRepo() *InMemoryRepo {
    return &InMemoryRepo{
        users: make(map[string]*User),
        rmap:  make(map[string]*RefreshToken),
    }
}

func (r *InMemoryRepo) CreateUser(ctx context.Context, u *User) error {
    r.mu.Lock()
    defer r.mu.Unlock()
    r.users[u.ID] = u
    return nil
}

func (r *InMemoryRepo) GetUserByID(ctx context.Context, id string) (*User, error) {
    r.mu.RLock()
    defer r.mu.RUnlock()
    u, ok := r.users[id]
    if !ok { return nil, ErrNotFound }
    return u, nil
}

func (r *InMemoryRepo) GetUserByProvider(ctx context.Context, provider, providerID string) (*User, error) {
    r.mu.RLock()
    defer r.mu.RUnlock()
    for _, u := range r.users {
        if u.Provider == provider && u.ProviderID == providerID {
            return u, nil
        }
    }
    return nil, ErrNotFound
}

func (r *InMemoryRepo) UpdateUser(ctx context.Context, u *User) error {
    r.mu.Lock()
    defer r.mu.Unlock()
    if _, ok := r.users[u.ID]; !ok { return ErrNotFound }
    r.users[u.ID] = u
    return nil
}

func (r *InMemoryRepo) AssignRole(ctx context.Context, userID, role string) error {
    r.mu.Lock()
    defer r.mu.Unlock()
    u, ok := r.users[userID]
    if !ok { return ErrNotFound }
    for _, rs := range u.Roles { if rs == role { return nil } }
    u.Roles = append(u.Roles, role)
    return nil
}

func (r *InMemoryRepo) RemoveRole(ctx context.Context, userID, role string) error {
    r.mu.Lock()
    defer r.mu.Unlock()
    u, ok := r.users[userID]
    if !ok { return ErrNotFound }
    newRoles := make([]string,0, len(u.Roles))
    for _, rs := range u.Roles { if rs != role { newRoles = append(newRoles, rs) } }
    u.Roles = newRoles
    return nil
}

func (r *InMemoryRepo) SetPermissions(ctx context.Context, userID string, perms []string) error {
    r.mu.Lock()
    defer r.mu.Unlock()
    u, ok := r.users[userID]
    if !ok { return ErrNotFound }
    u.Permissions = perms
    return nil
}

func (r *InMemoryRepo) SaveRefreshToken(ctx context.Context, rt *RefreshToken) error {
    r.mu.Lock()
    defer r.mu.Unlock()
    r.rmap[rt.Token] = rt
    return nil
}
func (r *InMemoryRepo) GetRefreshToken(ctx context.Context, token string) (*RefreshToken, error) {
    r.mu.RLock()
    defer r.mu.RUnlock()
    rt, ok := r.rmap[token]
    if !ok { return nil, ErrNotFound }
    if rt.ExpiresAt.Before(time.Now()) { return nil, ErrNotFound }
    return rt, nil
}
func (r *InMemoryRepo) DeleteRefreshToken(ctx context.Context, token string) error {
    r.mu.Lock()
    defer r.mu.Unlock()
    delete(r.rmap, token)
    return nil
}
