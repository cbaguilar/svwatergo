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
	ClientID      string
	AdminEmails   map[string]struct{}
	AllowedEmails map[string]struct{}
}

type Auth struct {
	cfg      AuthConfig
	verifier *oidc.IDTokenVerifier
	session  *SessionJWT
	users    UserStore
}

type Identity struct {
	Email   string
	Sub     string
	Name    string
	Picture string
}

type UserStore interface {
	IsAllowedEmail(ctx context.Context, email string) (bool, error)
	IsAdminEmail(ctx context.Context, email string) (bool, error)
	HasUsers(ctx context.Context) (bool, error)
}

type ctxKey int

const identityKey ctxKey = iota

func NewFromEnv(ctx context.Context) (*Auth, error) {
	clientID := strings.TrimSpace(os.Getenv("GOOGLE_CLIENT_ID"))
	if clientID == "" {
		return nil, fmt.Errorf("GOOGLE_CLIENT_ID is required")
	}
	admins := parseAllowlist(os.Getenv("ADMIN_EMAILS"))
	allowed := parseAllowlist(os.Getenv("ALLOWED_EMAILS"))

	provider, err := oidc.NewProvider(ctx, googleIssuer)
	if err != nil {
		return nil, fmt.Errorf("oidc provider: %w", err)
	}
	verifier := provider.Verifier(&oidc.Config{ClientID: clientID})
	session, err := NewSessionJWTFromEnv()
	if err != nil {
		return nil, err
	}

	return &Auth{
		cfg: AuthConfig{
			ClientID:      clientID,
			AdminEmails:   admins,
			AllowedEmails: allowed,
		},
		verifier: verifier,
		session:  session,
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

func AdminEmailsFromEnv() []string {
	return adminEmailsFromString(os.Getenv("ADMIN_EMAILS"))
}

func adminEmailsFromString(s string) []string {
	seen := parseAllowlist(s)
	out := make([]string, 0, len(seen))
	for email := range seen {
		out = append(out, email)
	}
	return out
}

func (a *Auth) Middleware() func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			identity, err := a.verifyRequest(r)
			if err != nil {
				code := http.StatusUnauthorized
				if isForbiddenErr(err) {
					code = http.StatusForbidden
				}
				http.Error(w, err.Error(), code)
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
			code := http.StatusUnauthorized
			if isForbiddenErr(err) {
				code = http.StatusForbidden
			}
			c.AbortWithStatusJSON(code, gin.H{"error": err.Error()})
			return
		}
		ctx := context.WithValue(c.Request.Context(), identityKey, identity)
		c.Request = c.Request.WithContext(ctx)
		c.Next()
	}
}

func (a *Auth) GinRequireAdmin() gin.HandlerFunc {
	return func(c *gin.Context) {
		id, ok := IdentityFromContext(c.Request.Context())
		if !ok {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "unauthorized"})
			return
		}
		isAdmin, err := a.IsAdmin(c.Request.Context(), id.Email)
		if err != nil || !isAdmin {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "forbidden"})
			return
		}
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
		isAdmin, err := a.IsAdmin(r.Context(), id.Email)
		if err != nil || !isAdmin {
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (a *Auth) AdminEmails() []string {
	if a == nil {
		return nil
	}
	out := make([]string, 0, len(a.cfg.AdminEmails))
	for email := range a.cfg.AdminEmails {
		out = append(out, email)
	}
	return out
}

func (a *Auth) AllowedEmails() []string {
	if a == nil {
		return nil
	}
	out := make([]string, 0, len(a.cfg.AllowedEmails))
	for email := range a.cfg.AllowedEmails {
		out = append(out, email)
	}
	return out
}

func (a *Auth) GoogleClientID() string {
	if a == nil {
		return ""
	}
	return a.cfg.ClientID
}

func (a *Auth) SessionEnabled() bool {
	return a != nil && a.session != nil && a.session.Enabled()
}

func (a *Auth) ExchangeGoogleToken(ctx context.Context, raw string) (Identity, string, time.Time, error) {
	id, _, err := a.verifyGoogleToken(ctx, raw)
	if err != nil {
		return Identity{}, "", time.Time{}, err
	}
	if err := a.ensureAllowed(ctx, id); err != nil {
		return Identity{}, "", time.Time{}, err
	}
	if !a.SessionEnabled() {
		return Identity{}, "", time.Time{}, fmt.Errorf("session jwt disabled")
	}
	jwt, exp, err := a.session.Issue(ctx, id)
	if err != nil {
		return Identity{}, "", time.Time{}, err
	}
	return id, jwt, exp, nil
}

func (a *Auth) SetUserStore(store UserStore) {
	if a == nil {
		return
	}
	a.users = store
}

func (a *Auth) IsAdmin(ctx context.Context, email string) (bool, error) {
	if a == nil {
		return false, nil
	}
	needle := strings.ToLower(strings.TrimSpace(email))
	if needle == "" {
		return false, nil
	}
	if _, ok := a.cfg.AdminEmails[needle]; ok {
		return true, nil
	}
	if a.users == nil {
		return false, nil
	}
	return a.users.IsAdminEmail(ctx, needle)
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
	token, err := bearerTokenFromRequest(r)
	if err != nil {
		return Identity{}, err
	}
	if token == "" {
		return Identity{}, fmt.Errorf("empty bearer token")
	}

	if v, ok := tokenCache.Load(token); ok {
		ct := v.(cachedToken)
		if time.Now().Before(ct.until) {
			if err := a.ensureAllowed(r.Context(), ct.id); err != nil {
				return Identity{}, err
			}
			return ct.id, nil
		}
		tokenCache.Delete(token)
	}

	if a.SessionEnabled() {
		if id, exp, err := a.session.Verify(r.Context(), token); err == nil {
			if err := a.ensureAllowed(r.Context(), id); err != nil {
				return Identity{}, err
			}
			tokenCache.Store(token, cachedToken{id: id, until: exp})
			return id, nil
		}
	}

	id, exp, err := a.verifyGoogleToken(r.Context(), token)
	if err != nil {
		return Identity{}, err
	}
	if err := a.ensureAllowed(r.Context(), id); err != nil {
		return Identity{}, err
	}
	tokenCache.Store(token, cachedToken{id: id, until: exp})
	return id, nil
}

func bearerTokenFromRequest(r *http.Request) (string, error) {
	authz := r.Header.Get("Authorization")
	if authz != "" {
		parts := strings.SplitN(authz, " ", 2)
		if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") {
			return "", fmt.Errorf("invalid Authorization header")
		}
		return strings.TrimSpace(parts[1]), nil
	}

	// Browser WebSocket clients cannot set Authorization headers during the handshake.
	if strings.EqualFold(r.Header.Get("Upgrade"), "websocket") {
		if token := strings.TrimSpace(r.URL.Query().Get("access_token")); token != "" {
			return token, nil
		}
	}

	return "", fmt.Errorf("missing Authorization header")
}

func (a *Auth) ensureAllowed(ctx context.Context, id Identity) error {
	if a == nil {
		return nil
	}
	needle := strings.ToLower(strings.TrimSpace(id.Email))
	if needle == "" {
		return fmt.Errorf("forbidden")
	}
	if _, ok := a.cfg.AdminEmails[needle]; ok {
		return nil
	}
	if _, ok := a.cfg.AllowedEmails[needle]; ok {
		return nil
	}
	if a.users != nil {
		allowed, err := a.users.IsAllowedEmail(ctx, needle)
		if err != nil {
			return fmt.Errorf("forbidden")
		}
		if allowed {
			return nil
		}
		hasUsers, err := a.users.HasUsers(ctx)
		if err != nil {
			return fmt.Errorf("forbidden")
		}
		// Preserve existing behavior: with no configured allowlist, auth is open.
		if hasUsers {
			return fmt.Errorf("forbidden")
		}
		if len(a.cfg.AllowedEmails) == 0 && len(a.cfg.AdminEmails) == 0 {
			return nil
		}
		return fmt.Errorf("forbidden")
	}
	if len(a.cfg.AllowedEmails) == 0 && len(a.cfg.AdminEmails) == 0 {
		return nil
	}
	return fmt.Errorf("forbidden")
}

func isForbiddenErr(err error) bool {
	return err != nil && err.Error() == "forbidden"
}

func (a *Auth) verifyGoogleToken(ctx context.Context, raw string) (Identity, time.Time, error) {
	idToken, err := a.verifier.Verify(ctx, raw)
	if err != nil {
		return Identity{}, time.Time{}, fmt.Errorf("invalid token")
	}

	var claims struct {
		Email         string `json:"email"`
		EmailVerified bool   `json:"email_verified"`
		Sub           string `json:"sub"`
		Name          string `json:"name"`
		Picture       string `json:"picture"`
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
		Email:   claims.Email,
		Sub:     claims.Sub,
		Name:    claims.Name,
		Picture: claims.Picture,
	}, exp, nil
}

func MustNewFromEnv(ctx context.Context) *Auth {
	a, err := NewFromEnv(ctx)
	if err != nil {
		log.Fatal(err)
	}
	return a
}
