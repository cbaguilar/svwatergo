# Apache + systemd setup for dual SVWaterGo backends

This setup runs two daemonized `svwatergo` instances:
- `dev` backend on `127.0.0.1:18080`
- `prod` backend on `127.0.0.1:28080` (real data)

Apache routes by header/query hint and includes automatic failover:
- Default: `prod`
- If `prod` is down: fallback to `dev`
- If request header `X-SVWater-Backend: dev` (or query `backend=dev`) is present: force `dev`

## 1) Build and place the backend binary

```bash
cd /home/cbaguilar/work/water/svwatergo
go build -o server ./cmd/server
sudo mkdir -p /opt/svwatergo /opt/svwatergo/data
sudo cp ./server /opt/svwatergo/server
```

## 2) Install and configure systemd instances

```bash
sudo mkdir -p /etc/svwatergo
sudo cp deploy/apache/systemd/svwatergo@.service /etc/systemd/system/
sudo cp deploy/apache/env/dev.env.example /etc/svwatergo/dev.env
sudo cp deploy/apache/env/prod.env.example /etc/svwatergo/prod.env
# edit env files for DATABASE_URL/auth/secrets as needed
sudo systemctl daemon-reload
sudo systemctl enable --now svwatergo@dev svwatergo@prod
sudo systemctl status svwatergo@dev svwatergo@prod --no-pager
```

## 3) Apache config (two options)

For your current server layout (recommended for you), patch the existing
`/etc/apache2/sites-enabled/000-default.conf` `*:443` block for `svwaternet.org`.
Use this snippet:

`deploy/apache/apache/svwatergo-existing-vhost-snippet.conf`

Replace only the old Go API rules (`/api` and websocket `/state/stream`), and keep your existing:
- TLS cert lines
- `ProxyPass / http://127.0.0.1:4200/` frontend rule
- other vhosts (like `cm.svwaternet.org`)

If you want a separate dedicated API vhost instead, use:
- `deploy/apache/apache/svwatergo-header-routing.conf`

### Enable required Apache modules

```bash
sudo a2enmod proxy proxy_http proxy_balancer lbmethod_byrequests rewrite headers
sudo apachectl configtest
sudo systemctl reload apache2
```

If you need TLS, use the commented `*:443` block in `svwatergo-header-routing.conf` and enable `ssl`:

```bash
sudo a2enmod ssl
sudo systemctl reload apache2
```

## 4) Verify routing behavior

Default route (prod, with auto fallback if prod is dead):

```bash
curl -i http://api.svwaternet.org/health
```

Forced dev route:

```bash
curl -i -H 'X-SVWater-Backend: dev' http://api.svwaternet.org/health
```

Forced dev route (query-string form, useful for browser websocket flows):

```bash
curl -i 'http://api.svwaternet.org/health?backend=dev'
```

Browser websocket clients can force dev using `?backend=dev`.

## Notes

- `cmd/server/main.go` now honors `APP_PORT` (default `8080`) so multiple instances can run simultaneously.
- The backend also loads `.env` from its working directory, but variables in `/etc/svwatergo/*.env` win because they are already set by systemd.
