package oauth

import (
	"sync"
	"time"
)

type Storage struct {
	mu            sync.RWMutex
	codes         map[string]storedCode
	refreshTokens map[string]storedRefresh
	attempts      map[string]attemptInfo
	users         map[string]User
}

type User struct {
	Identifier string
	Role       string
}

type storedCode struct {
	Code      string
	ExpiresAt time.Time
}

type storedRefresh struct {
	Token     string
	ExpiresAt time.Time
}

type attemptInfo struct {
	Count     int
	ExpiresAt time.Time
}

func NewStorage() *Storage {
	s := &Storage{
		codes:         make(map[string]storedCode),
		refreshTokens: make(map[string]storedRefresh),
		attempts:      make(map[string]attemptInfo),
		users:         make(map[string]User),
	}

	s.users["admin1"] = User{
		Identifier: "admin1",
		Role:       "admin",
	}

	s.users["user1"] = User{
		Identifier: "user1",
		Role:       "user",
	}

	return s
}

func (s *Storage) SaveCode(identifier, code string, ttl time.Duration) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.codes[identifier] = storedCode{
		Code:      code,
		ExpiresAt: time.Now().Add(ttl),
	}
}

func (s *Storage) GetCode(identifier string) (string, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	data, ok := s.codes[identifier]
	if !ok || time.Now().After(data.ExpiresAt) {
		return "", false
	}
	return data.Code, true
}

func (s *Storage) DeleteCode(identifier string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.codes, identifier)
}

func (s *Storage) CleanupExpiredCodes() {
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now()
	for id, data := range s.codes {
		if now.After(data.ExpiresAt) {
			delete(s.codes, id)
		}
	}
}

func (s *Storage) RegisterAttempt(identifier string) (int, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	data, ok := s.attempts[identifier]
	if !ok || time.Now().After(data.ExpiresAt) {
		s.attempts[identifier] = attemptInfo{
			Count:     1,
			ExpiresAt: time.Now().Add(10 * time.Minute),
		}
		return 1, true
	}

	data.Count++
	s.attempts[identifier] = data
	return data.Count, data.Count <= 5
}

func (s *Storage) CleanupExpiredAttempts() {
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now()
	for id, data := range s.attempts {
		if now.After(data.ExpiresAt) {
			delete(s.attempts, id)
		}
	}
}

func (s *Storage) SaveRefreshToken(identifier, token string, ttl time.Duration) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.refreshTokens[identifier] = storedRefresh{
		Token:     token,
		ExpiresAt: time.Now().Add(ttl),
	}
}

func (s *Storage) GetRefreshToken(identifier string) (string, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	data, ok := s.refreshTokens[identifier]
	if !ok || time.Now().After(data.ExpiresAt) {
		return "", false
	}
	return data.Token, true
}

func (s *Storage) FindIdentifierByRefreshToken(refresh string) (string, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	for identifier, data := range s.refreshTokens {
		if data.Token == refresh {
			if time.Now().After(data.ExpiresAt) {
				return "", false
			}
			return identifier, true
		}
	}
	return "", false
}

func (s *Storage) CleanupExpiredRefreshTokens() {
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now()
	for id, data := range s.refreshTokens {
		if now.After(data.ExpiresAt) {
			delete(s.refreshTokens, id)
		}
	}
}

func (s *Storage) GetUserRole(identifier string) string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if user, ok := s.users[identifier]; ok {
		return user.Role
	}
	return "user"
}

func (s *Storage) SetUserRole(identifier, role string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.users[identifier] = User{
		Identifier: identifier,
		Role:       role,
	}
}
