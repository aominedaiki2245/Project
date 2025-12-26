package main

import (
    "crypto/rsa"
    "crypto/x509"
    "encoding/json"
    "encoding/pem"
    "errors"
    "io/ioutil"
    "time"

    "github.com/golang-jwt/jwt/v5"
)

type JWTManager struct {
    privateKey *rsa.PrivateKey
    publicKey  *rsa.PublicKey
    issuer     string
    audience   string
    expire     time.Duration
}

func NewJWTManager(privPemPath, pubPemPath, issuer, audience string, expireMinutes int) (*JWTManager, error) {
    privPEM, err := ioutil.ReadFile(privPemPath)
    if err != nil { return nil, err }
    block, _ := pem.Decode(privPEM)
    if block == nil { return nil, errors.New("invalid private key pem") }
    privKey, err := x509.ParsePKCS1PrivateKey(block.Bytes)
    if err != nil { return nil, err }

    pubPEM, err := ioutil.ReadFile(pubPemPath)
    if err != nil { return nil, err }
    block2, _ := pem.Decode(pubPEM)
    if block2 == nil { return nil, errors.New("invalid public key pem") }
    pubInterface, err := x509.ParsePKIXPublicKey(block2.Bytes)
    if err != nil { return nil, err }
    pubKey, ok := pubInterface.(*rsa.PublicKey)
    if !ok { return nil, errors.New("not rsa public key") }

    return &JWTManager{
        privateKey: privKey,
        publicKey:  pubKey,
        issuer: issuer,
        audience: audience,
        expire: time.Duration(expireMinutes) * time.Minute,
    }, nil
}

type TokenClaims struct {
    UserID      string   `json:"userId"`
    Roles       []string `json:"roles"`
    Permissions []string `json:"permissions"`
    jwt.RegisteredClaims
}

func (m *JWTManager) GenerateToken(u *User) (string, time.Time, error) {
    now := time.Now().UTC()
    exp := now.Add(m.expire)
    claims := TokenClaims{
        UserID: u.ID,
        Roles: u.Roles,
        Permissions: u.Permissions,
        RegisteredClaims: jwt.RegisteredClaims{
            Issuer: m.issuer,
            Audience: jwt.ClaimStrings{m.audience},
            IssuedAt: jwt.NewNumericDate(now),
            ExpiresAt: jwt.NewNumericDate(exp),
            Subject: u.ID,
        },
    }
    tok := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
    signed, err := tok.SignedString(m.privateKey)
    return signed, exp, err
}

func (m *JWTManager) VerifyToken(tokenStr string) (*TokenClaims, error) {
    token, err := jwt.ParseWithClaims(tokenStr, &TokenClaims{}, func(t *jwt.Token) (interface{}, error) {
        if _, ok := t.Method.(*jwt.SigningMethodRSA); !ok {
            return nil, errors.New("unexpected signing method")
        }
        return m.publicKey, nil
    })
    if err != nil { return nil, err }
    if claims, ok := token.Claims.(*TokenClaims); ok && token.Valid {
        return claims, nil
    }
    return nil, errors.New("invalid token")
}

// JWKS minimal publish (kid not implemented in depth)
func (m *JWTManager) JwksJSON() ([]byte, error) {
    // Build a rudimentary JWK from RSA public key. For production use full fields & kid.
    // Here we convert public key to pkix and base64 encode modulus/exponent if needed.
    // For brevity — return minimal info: use x5c (base64 cert) or modulus/exponent (omitted complex encoding).
    // Simpler approach: publish PEM as public key (not strict JWKS) — main service uses /verify endpoint anyway.
    jw := map[string]interface{}{
        "keys": []map[string]string{
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "pem": string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: x509.MarshalPKCS1PublicKey(m.publicKey)})),
            },
        },
    }
    return json.Marshal(jw)
}
