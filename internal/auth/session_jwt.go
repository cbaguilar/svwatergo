package auth

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"
)

const sessionIssuer = "svwatergo"

type SessionConfig struct {
	Secret []byte
	TTL    time.Duration
}

type SessionJWT struct {
	cfg SessionConfig
}

type SessionClaims struct {
	Iss     string `json:"iss"`
	Sub     string `json:"sub"`
	Email   string `json:"email"`
	Name    string `json:"name,omitempty"`
	Picture string `json:"picture,omitempty"`
	Iat     int64  `json:"iat"`
	Exp     int64  `json:"exp"`
}

func NewSessionJWTFromEnv() (*SessionJWT, error) {
	secret := strings.TrimSpace(os.Getenv("JWT_SECRET"))
	if secret == "" {
		return nil, nil
	}

	ttl := 24 * time.Hour
	if raw := strings.TrimSpace(os.Getenv("JWT_TTL")); raw != "" {
		parsed, err := time.ParseDuration(raw)
		if err != nil {
			return nil, fmt.Errorf("invalid JWT_TTL: %w", err)
		}
		if parsed <= 0 {
			return nil, fmt.Errorf("JWT_TTL must be > 0")
		}
		ttl = parsed
	}

	return &SessionJWT{
		cfg: SessionConfig{
			Secret: []byte(secret),
			TTL:    ttl,
		},
	}, nil
}

func (s *SessionJWT) Enabled() bool {
	return s != nil && len(s.cfg.Secret) > 0
}

func (s *SessionJWT) Issue(_ context.Context, id Identity) (string, time.Time, error) {
	if !s.Enabled() {
		return "", time.Time{}, fmt.Errorf("session jwt disabled")
	}

	now := time.Now().UTC()
	exp := now.Add(s.cfg.TTL)
	claims := SessionClaims{
		Iss:     sessionIssuer,
		Sub:     id.Sub,
		Email:   id.Email,
		Name:    id.Name,
		Picture: id.Picture,
		Iat:     now.Unix(),
		Exp:     exp.Unix(),
	}

	headerJSON, err := json.Marshal(map[string]string{
		"alg": "HS256",
		"typ": "JWT",
	})
	if err != nil {
		return "", time.Time{}, err
	}
	payloadJSON, err := json.Marshal(claims)
	if err != nil {
		return "", time.Time{}, err
	}

	enc := base64.RawURLEncoding
	header := enc.EncodeToString(headerJSON)
	payload := enc.EncodeToString(payloadJSON)
	signingInput := header + "." + payload
	sig := signHS256([]byte(signingInput), s.cfg.Secret)
	token := signingInput + "." + enc.EncodeToString(sig)
	return token, exp, nil
}

func (s *SessionJWT) Verify(_ context.Context, raw string) (Identity, time.Time, error) {
	if !s.Enabled() {
		return Identity{}, time.Time{}, fmt.Errorf("session jwt disabled")
	}
	parts := strings.Split(raw, ".")
	if len(parts) != 3 {
		return Identity{}, time.Time{}, fmt.Errorf("invalid token")
	}

	enc := base64.RawURLEncoding
	signingInput := parts[0] + "." + parts[1]
	gotSig, err := enc.DecodeString(parts[2])
	if err != nil {
		return Identity{}, time.Time{}, fmt.Errorf("invalid token")
	}
	wantSig := signHS256([]byte(signingInput), s.cfg.Secret)
	if !hmac.Equal(gotSig, wantSig) {
		return Identity{}, time.Time{}, fmt.Errorf("invalid token")
	}

	headerRaw, err := enc.DecodeString(parts[0])
	if err != nil {
		return Identity{}, time.Time{}, fmt.Errorf("invalid token")
	}
	var header struct {
		Alg string `json:"alg"`
		Typ string `json:"typ"`
	}
	if err := json.Unmarshal(headerRaw, &header); err != nil {
		return Identity{}, time.Time{}, fmt.Errorf("invalid token")
	}
	if header.Alg != "HS256" {
		return Identity{}, time.Time{}, fmt.Errorf("invalid token")
	}

	payloadRaw, err := enc.DecodeString(parts[1])
	if err != nil {
		return Identity{}, time.Time{}, fmt.Errorf("invalid token")
	}
	var claims SessionClaims
	if err := json.Unmarshal(payloadRaw, &claims); err != nil {
		return Identity{}, time.Time{}, fmt.Errorf("invalid token")
	}
	if claims.Iss != sessionIssuer || claims.Email == "" || claims.Sub == "" {
		return Identity{}, time.Time{}, fmt.Errorf("invalid token")
	}
	exp := time.Unix(claims.Exp, 0)
	if claims.Exp <= 0 || time.Now().After(exp) {
		return Identity{}, time.Time{}, fmt.Errorf("token expired")
	}

	return Identity{
		Email:   claims.Email,
		Sub:     claims.Sub,
		Name:    claims.Name,
		Picture: claims.Picture,
	}, exp, nil
}

func signHS256(data []byte, secret []byte) []byte {
	mac := hmac.New(sha256.New, secret)
	mac.Write(data)
	return mac.Sum(nil)
}
