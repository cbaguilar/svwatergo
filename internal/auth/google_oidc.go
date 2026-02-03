package auth

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/coreos/go-oidc/v3/oidc"
	"github.com/gin-gonic/gin"
)

const googleIssuer = "https://accounts.google.com"

type AuthConfig struct {
	ClientID    string
	AdminEmails map[string]struct{}
}

type Auth struct {
	cfg      AuthConfig
	verifier *oidc.IDTokenVerifier
}

type Identity struct {
	Email string
	Sub   string
}

type ctxKey int

const identityKey ctxKey = iota

func NewFromEnv(ctx context.Context) (*Auth, error) {
	clientID := strings.TrimSpace(os.Getenv("GOOGLE_CLIENT_ID"))
	if clientID == "" {
		return nil, fmt.Errorf("GOOGLE_CLIENT_ID is required")
	}
	admins := parseAllowlist(os.Getenv("ADMIN_EMAILS"))

	provider, err := oidc.NewProvider(ctx, googleIssuer)
	if err != nil {
		return nil, fmt.Errorf("oidc provider: %w", err)
	}
	verifier := provider.Verifier(&oidc.Config{ClientID: clientID})

	return &Auth{
		cfg: AuthConfig{
			ClientID:    clientID,
			AdminEmails: admins,
		},
		verifier: verifier,
	}, nil
}

func parseAllowlist(s string) map[string]struct{} {
	out := map[string]struct{}{}
	for _, part := range strings.Split(s, ",") {
		p := strings.ToLower(strings.TrimSpace(part))
		if p == "" {
			continue
		}
		out[p] = struct{}{}
	}
	return out
}

func (a *Auth) Middleware() func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			identity, err := a.verifyRequest(r)
			if err != nil {
				http.Error(w, err.Error(), http.StatusUnauthorized)
				return
			}
			ctx := context.WithValue(r.Context(), identityKey, identity)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func (a *Auth) GinMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		identity, err := a.verifyRequest(c.Request)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": err.Error()})
			return
		}
		ctx := context.WithValue(c.Request.Context(), identityKey, identity)
		c.Request = c.Request.WithContext(ctx)
		c.Next()
	}
}

func (a *Auth) RequireAdmin(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id, ok := IdentityFromContext(r.Context())
		if !ok {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		if _, ok := a.cfg.AdminEmails[strings.ToLower(id.Email)]; !ok {
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func IdentityFromContext(ctx context.Context) (Identity, bool) {
	v := ctx.Value(identityKey)
	if v == nil {
		return Identity{}, false
	}
	id, ok := v.(Identity)
	return id, ok
}

type cachedToken struct {
	id    Identity
	until time.Time
}

var tokenCache sync.Map

func (a *Auth) verifyRequest(r *http.Request) (Identity, error) {
	authz := r.Header.Get("Authorization")
	if authz == "" {
		return Identity{}, fmt.Errorf("missing Authorization header")
	}
	parts := strings.SplitN(authz, " ", 2)
	if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") {
		return Identity{}, fmt.Errorf("invalid Authorization header")
	}
	token := strings.TrimSpace(parts[1])
	if token == "" {
		return Identity{}, fmt.Errorf("empty bearer token")
	}

	if v, ok := tokenCache.Load(token); ok {
		ct := v.(cachedToken)
		if time.Now().Before(ct.until) {
			return ct.id, nil
		}
		tokenCache.Delete(token)
	}

	id, exp, err := a.verifyToken(r.Context(), token)
	if err != nil {
		return Identity{}, err
	}
	tokenCache.Store(token, cachedToken{id: id, until: exp})
	return id, nil
}

func (a *Auth) verifyToken(ctx context.Context, raw string) (Identity, time.Time, error) {
	idToken, err := a.verifier.Verify(ctx, raw)
	if err != nil {
		return Identity{}, time.Time{}, fmt.Errorf("invalid token")
	}

	var claims struct {
		Email         string `json:"email"`
		EmailVerified bool   `json:"email_verified"`
		Sub           string `json:"sub"`
	}
	if err := idToken.Claims(&claims); err != nil {
		return Identity{}, time.Time{}, fmt.Errorf("invalid token claims")
	}
	if !claims.EmailVerified || claims.Email == "" {
		return Identity{}, time.Time{}, fmt.Errorf("email not verified")
	}

	exp := idToken.Expiry
	if exp.IsZero() {
		exp = time.Now().Add(10 * time.Minute)
	}

	return Identity{
		Email: claims.Email,
		Sub:   claims.Sub,
	}, exp, nil
}

func MustNewFromEnv(ctx context.Context) *Auth {
	a, err := NewFromEnv(ctx)
	if err != nil {
		log.Fatal(err)
	}
	return a
}
