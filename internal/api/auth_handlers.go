package api

import (
	"net/http"
	"strings"

	"github.com/cbaguilar/svwatergo/internal/auth"
	"github.com/gin-gonic/gin"
)

type AuthAPI struct {
	authn *auth.Auth
}

func NewAuthAPI(authn *auth.Auth) *AuthAPI {
	return &AuthAPI{authn: authn}
}

func (a *AuthAPI) GetConfig(c *gin.Context) {
	if a == nil || a.authn == nil {
		c.JSON(http.StatusOK, gin.H{
			"enabled":        false,
			"googleClientId": "",
			"sessionJwt":     false,
		})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"enabled":        true,
		"googleClientId": a.authn.GoogleClientID(),
		"sessionJwt":     a.authn.SessionEnabled(),
	})
}

func (a *AuthAPI) ExchangeGoogle(c *gin.Context) {
	if a == nil || a.authn == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "auth is disabled"})
		return
	}
	if !a.authn.SessionEnabled() {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "JWT sessions are not configured"})
		return
	}

	var req struct {
		Credential string `json:"credential"`
		IDToken    string `json:"id_token"`
		Token      string `json:"token"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
		return
	}

	raw := strings.TrimSpace(req.Credential)
	if raw == "" {
		raw = strings.TrimSpace(req.IDToken)
	}
	if raw == "" {
		raw = strings.TrimSpace(req.Token)
	}
	if raw == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "missing Google credential"})
		return
	}

	id, token, exp, err := a.authn.ExchangeGoogleToken(c.Request.Context(), raw)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"token": token,
		"user": gin.H{
			"email":   id.Email,
			"sub":     id.Sub,
			"name":    id.Name,
			"picture": id.Picture,
		},
		"expiresAt": exp.UTC().Format(timeRFC3339),
	})
}

func (a *AuthAPI) Me(c *gin.Context) {
	id, ok := auth.IdentityFromContext(c.Request.Context())
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "unauthorized"})
		return
	}

	isAdmin := false
	if a != nil && a.authn != nil {
		v, err := a.authn.IsAdmin(c.Request.Context(), id.Email)
		if err == nil {
			isAdmin = v
		}
	}
	c.JSON(http.StatusOK, gin.H{
		"user": gin.H{
			"email":   id.Email,
			"sub":     id.Sub,
			"name":    id.Name,
			"picture": id.Picture,
		},
		"isAdmin": isAdmin,
	})
}

const timeRFC3339 = "2006-01-02T15:04:05Z07:00"
