package api

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/cbaguilar/svwatergo/internal/metadata"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/gin-gonic/gin"
	"github.com/lib/pq"
	"golang.org/x/net/websocket"
)

type liveClient struct {
	ch          chan []byte
	includeSoft bool
}

const (
	pgLiveStateChannel = "svwatergo_live_state_updates"
	pgListenMinRetry   = 5 * time.Second
	pgListenMaxRetry   = 1 * time.Minute
)

type liveStateNotification struct {
	Site   string `json:"site"`
	Sender string `json:"sender,omitempty"`
}

type LiveStateAPI struct {
	Reg     systemservice.Registry
	Meta    *metadata.Store
	mu      sync.RWMutex
	clients map[string]map[*liveClient]struct{}
	db      *database.SQLXClient
	selfID  string
}

func NewLiveStateAPI(reg systemservice.Registry, meta *metadata.Store, db *database.SQLXClient) *LiveStateAPI {
	a := &LiveStateAPI{
		Reg:     reg,
		Meta:    meta,
		clients: map[string]map[*liveClient]struct{}{},
		db:      db,
		selfID:  generateLiveStateSenderID(),
	}
	if a.pgEnabled() {
		go a.listenForPostgresUpdates(db.Conn)
	}
	return a
}

func (a *LiveStateAPI) StreamLatest(c *gin.Context) {
	site := strings.ToLower(c.Param("site"))
	if _, ok := a.Reg.Get(site); !ok {
		c.JSON(http.StatusNotFound, errJSON("NotFound", "unknown site", gin.H{"site": site}))
		return
	}

	includeSoft := parseSoftInclude(c.Query("soft"))
	h := websocket.Handler(func(ws *websocket.Conn) {
		defer ws.Close()

		client := &liveClient{ch: make(chan []byte, 16), includeSoft: includeSoft}
		a.addClient(site, client)
		defer a.removeClient(site, client)

		if msg, err := a.buildLatestMessage(site, includeSoft); err == nil && msg != nil {
			if err := websocket.Message.Send(ws, string(msg)); err != nil {
				return
			}
		}

		done := make(chan struct{})
		go func() {
			defer close(done)
			for msg := range client.ch {
				if err := websocket.Message.Send(ws, string(msg)); err != nil {
					return
				}
			}
		}()

		for {
			var in string
			if err := websocket.Message.Receive(ws, &in); err != nil {
				return
			}
			select {
			case <-done:
				return
			default:
			}
		}
	})

	h.ServeHTTP(c.Writer, c.Request)
}

func (a *LiveStateAPI) NotifySiteUpdated(site string) {
	site = strings.ToLower(strings.TrimSpace(site))
	if site == "" {
		return
	}
	a.notifySiteUpdatedLocal(site)
	a.publishPostgresUpdate(site)
}

func (a *LiveStateAPI) notifySiteUpdatedLocal(site string) {
	a.mu.RLock()
	siteClients := a.clients[site]
	a.mu.RUnlock()
	if len(siteClients) == 0 {
		return
	}

	msgNoSoft, err := a.buildLatestMessage(site, false)
	if err != nil {
		log.Printf("stream build latest for %s failed: %v", site, err)
		return
	}
	if msgNoSoft == nil {
		return
	}

	var msgSoft []byte
	for client := range siteClients {
		msg := msgNoSoft
		if client.includeSoft {
			if msgSoft == nil {
				m, err := a.buildLatestMessage(site, true)
				if err != nil || m == nil {
					continue
				}
				msgSoft = m
			}
			msg = msgSoft
		}
		a.trySend(client, msg)
	}
}

func (a *LiveStateAPI) pgEnabled() bool {
	return a != nil && a.db != nil && a.db.Driver == "postgres" && strings.TrimSpace(a.db.Conn) != ""
}

func (a *LiveStateAPI) publishPostgresUpdate(site string) {
	if !a.pgEnabled() {
		return
	}
	payload, err := json.Marshal(liveStateNotification{Site: site, Sender: a.selfID})
	if err != nil {
		log.Printf("stream notify marshal failed for %s: %v", site, err)
		return
	}
	if _, err := a.db.DB.ExecContext(context.Background(), "SELECT pg_notify($1, $2)", pgLiveStateChannel, string(payload)); err != nil {
		log.Printf("stream notify publish failed for %s: %v", site, err)
	}
}

func (a *LiveStateAPI) listenForPostgresUpdates(conn string) {
	listener := pq.NewListener(conn, pgListenMinRetry, pgListenMaxRetry, func(event pq.ListenerEventType, err error) {
		if err != nil {
			log.Printf("stream notify listener event %v: %v", event, err)
		}
	})
	defer listener.Close()

	if err := listener.Listen(pgLiveStateChannel); err != nil {
		log.Printf("stream notify LISTEN failed on %s: %v", pgLiveStateChannel, err)
		return
	}
	log.Printf("stream notify LISTEN enabled on %s", pgLiveStateChannel)

	for {
		select {
		case n := <-listener.Notify:
			if n == nil {
				_ = listener.Ping()
				continue
			}
			site, sender := parseLiveStateNotification(n.Extra)
			if site == "" || sender == a.selfID {
				continue
			}
			a.notifySiteUpdatedLocal(site)
		case <-time.After(90 * time.Second):
			_ = listener.Ping()
		}
	}
}

func parseLiveStateNotification(payload string) (site string, sender string) {
	payload = strings.TrimSpace(payload)
	if payload == "" {
		return "", ""
	}
	var n liveStateNotification
	if err := json.Unmarshal([]byte(payload), &n); err == nil {
		return strings.ToLower(strings.TrimSpace(n.Site)), strings.TrimSpace(n.Sender)
	}
	// Backward compatible fallback in case sender publishes raw site text.
	return strings.ToLower(payload), ""
}

func generateLiveStateSenderID() string {
	host := "svwatergo"
	if h, err := os.Hostname(); err == nil {
		if s := strings.TrimSpace(h); s != "" {
			host = s
		}
	}
	b := make([]byte, 6)
	if _, err := rand.Read(b); err != nil {
		return host + "-" + time.Now().UTC().Format("20060102T150405.000000000")
	}
	return host + "-" + hex.EncodeToString(b)
}

func (a *LiveStateAPI) buildLatestMessage(site string, includeSoft bool) ([]byte, error) {
	mgr, ok := a.Reg.Get(site)
	if !ok {
		return nil, nil
	}
	data, err := mgr.GetLatest()
	if err != nil {
		return nil, err
	}
	if includeSoft {
		addSoftSensors(a.Meta, site, data)
	}

	payload := gin.H{
		"type": "state.latest",
		"meta": gin.H{
			"site":          site,
			"streamed_at":   time.Now().UTC().Format(time.RFC3339),
			"soft_included": includeSoft,
		},
		"data": data,
	}
	return json.Marshal(payload)
}

func (a *LiveStateAPI) addClient(site string, client *liveClient) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if _, ok := a.clients[site]; !ok {
		a.clients[site] = map[*liveClient]struct{}{}
	}
	a.clients[site][client] = struct{}{}
}

func (a *LiveStateAPI) removeClient(site string, client *liveClient) {
	a.mu.Lock()
	defer a.mu.Unlock()
	siteClients, ok := a.clients[site]
	if !ok {
		return
	}
	delete(siteClients, client)
	close(client.ch)
	if len(siteClients) == 0 {
		delete(a.clients, site)
	}
}

func (a *LiveStateAPI) trySend(client *liveClient, msg []byte) {
	select {
	case client.ch <- msg:
	default:
		select {
		case <-client.ch:
		default:
		}
		select {
		case client.ch <- msg:
		default:
		}
	}
}
