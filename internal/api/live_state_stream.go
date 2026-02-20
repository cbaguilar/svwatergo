package api

import (
	"encoding/json"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/cbaguilar/svwatergo/internal/metadata"
	"github.com/cbaguilar/svwatergo/internal/systemservice"
	"github.com/gin-gonic/gin"
	"golang.org/x/net/websocket"
)

type liveClient struct {
	ch          chan []byte
	includeSoft bool
}

type LiveStateAPI struct {
	Reg     systemservice.Registry
	Meta    *metadata.Store
	mu      sync.RWMutex
	clients map[string]map[*liveClient]struct{}
}

func NewLiveStateAPI(reg systemservice.Registry, meta *metadata.Store) *LiveStateAPI {
	return &LiveStateAPI{
		Reg:     reg,
		Meta:    meta,
		clients: map[string]map[*liveClient]struct{}{},
	}
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
