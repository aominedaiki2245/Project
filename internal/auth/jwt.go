package auth

import "errors"

func ValidateAccessToken(token string) (bool, error) {
	if token == "" {
		return false, errors.New("empty token")
	}

	// ПОКА ЗАГЛУШКА
	if token == "valid-token" {
		return true, nil
	}

	return false, errors.New("invalid token")
}