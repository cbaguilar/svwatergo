package api

import (
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
)

const (
	apiRequestsPerSecond = 2.0
	apiRequestBurst      = 15.0
	maxRateLimitClients  = 10000
)

type requestBucket struct {
	tokens   float64
	updated  time.Time
	lastSeen time.Time
}

type apiRateLimiter struct {
	mu        sync.Mutex
	clients   map[string]*requestBucket
	lastSweep time.Time
}

func newAPIRateLimiter() *apiRateLimiter {
	return &apiRateLimiter{clients: make(map[string]*requestBucket)}
}

func (l *apiRateLimiter) allow(client string, now time.Time) bool {
	if client == "" {
		client = "unknown"
	}

	l.mu.Lock()
	defer l.mu.Unlock()

	if now.Sub(l.lastSweep) >= time.Minute {
		for ip, bucket := range l.clients {
			if now.Sub(bucket.lastSeen) > 10*time.Minute {
				delete(l.clients, ip)
			}
		}
		l.lastSweep = now
	}

	bucket, ok := l.clients[client]
	if !ok {
		if len(l.clients) >= maxRateLimitClients {
			return false
		}
		bucket = &requestBucket{tokens: apiRequestBurst, updated: now, lastSeen: now}
		l.clients[client] = bucket
	}

	bucket.tokens += now.Sub(bucket.updated).Seconds() * apiRequestsPerSecond
	if bucket.tokens > apiRequestBurst {
		bucket.tokens = apiRequestBurst
	}
	bucket.updated = now
	bucket.lastSeen = now
	if bucket.tokens < 1 {
		return false
	}
	bucket.tokens--
	return true
}

func apiRequestRateLimit() gin.HandlerFunc {
	limiter := newAPIRateLimiter()
	return func(c *gin.Context) {
		if !strings.HasPrefix(c.Request.URL.Path, "/api/") {
			c.Next()
			return
		}
		if limiter.allow(requestClientIP(c.Request), time.Now()) {
			c.Next()
			return
		}
		c.Header("Retry-After", "1")
		c.AbortWithStatusJSON(http.StatusTooManyRequests, gin.H{
			"error": gin.H{"code": "RateLimited", "message": "too many requests; retry shortly"},
		})
	}
}

func requestClientIP(r *http.Request) string {
	if ip := net.ParseIP(strings.TrimSpace(r.Header.Get("X-SVWater-Client-IP"))); ip != nil {
		return ip.String()
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err == nil {
		if ip := net.ParseIP(host); ip != nil {
			return ip.String()
		}
	}
	return r.RemoteAddr
}
