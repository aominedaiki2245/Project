package oauth

import (
	"time"

	"github.com/golang-jwt/jwt/v5"
)

var secretKey = []byte("SUPER_SECRET_KEY")

type Claims struct {
	Identifier  string   `json:"id"`
	Permissions []string `json:"permissions"`
	jwt.RegisteredClaims
}

func GenerateTokens(identifier string, permissions []string) (string, string) {
	claims := Claims{
		Identifier:  identifier,
		Permissions: permissions,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(15 * time.Minute)),
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	access, _ := token.SignedString(secretKey)

	refreshClaims := jwt.RegisteredClaims{
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(24 * time.Hour)),
		Subject:   identifier,
	}
	refreshToken := jwt.NewWithClaims(jwt.SigningMethodHS256, refreshClaims)
	refresh, _ := refreshToken.SignedString(secretKey)

	return access, refresh
}

func ValidateToken(tokenStr string) (*Claims, error) {
	token, err := jwt.ParseWithClaims(tokenStr, &Claims{}, func(token *jwt.Token) (interface{}, error) {
		return secretKey, nil
	})
	if err != nil {
		return nil, err
	}
	if claims, ok := token.Claims.(*Claims); ok && token.Valid {
		return claims, nil
	}
	return nil, err
}
