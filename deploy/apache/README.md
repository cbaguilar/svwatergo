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

## mTLS rollout snippets

To validate client-certificate auth without touching live uploads first, add:
- `deploy/apache/apache/svwatergo-mtls-probe-snippet.conf`

That protects only:
- `POST /api/v1/ingest/mtls-probe`

The backend exposes that probe route directly so Apache mTLS can be tested
without application auth or upload side effects.

When you are ready to enforce mTLS on uploads too, add:
- `deploy/apache/apache/svwatergo-mtls-all-ingest-snippet.conf`

That protects:
- `/api/v1/ingest/mtls-probe`
- `/UploadDataNew`
- `/uploadDataNew`
- `/uploadSensorDataNew`

Both mTLS snippets assume your existing TLS vhost also includes:

```apache
SSLCACertificateFile /etc/apache2/ssl/upload-client-ca.pem
SSLVerifyClient optional
SSLVerifyDepth 2
SSLOptions +StdEnvVars +ExportCertData
```

### Generate a private client CA and uploader certs

Helper script:
- `deploy/apache/scripts/generate-mtls-materials.sh`

Create the CA Apache will trust:

```bash
mkdir -p deploy/apache/mtls
deploy/apache/scripts/generate-mtls-materials.sh ca upload-client deploy/apache/mtls
```

That produces:
- `deploy/apache/mtls/upload-client-ca.key`
- `deploy/apache/mtls/upload-client-ca.pem`

Issue one client cert per uploader:

```bash
deploy/apache/scripts/generate-mtls-materials.sh client uploader-01 deploy/apache/mtls
```

That produces:
- `deploy/apache/mtls/uploader-01.key`
- `deploy/apache/mtls/uploader-01.csr`
- `deploy/apache/mtls/uploader-01.crt`

Install the CA cert on Apache as:

```bash
sudo install -m 0644 deploy/apache/mtls/upload-client-ca.pem /etc/apache2/ssl/upload-client-ca.pem
```

Keep the CA private key off the Apache host if possible. Only the CA cert
belongs on Apache; the CA key stays where you issue client certs.

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

For the mTLS snippets, `headers` and `ssl` must both be enabled.

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

### Verify mTLS probe

Without a client cert, the probe should fail with `403`:

```bash
curl -i -X POST https://svwaternet.org/api/v1/ingest/mtls-probe
```

With a valid client cert, it should return `200`:

```bash
curl -i -X POST \
  --cert /path/to/uploader.crt \
  --key /path/to/uploader.key \
  https://svwaternet.org/api/v1/ingest/mtls-probe
```

## Notes

- `cmd/server/main.go` now honors `APP_PORT` (default `8080`) so multiple instances can run simultaneously.
- The backend also loads `.env` from its working directory, but variables in `/etc/svwatergo/*.env` win because they are already set by systemd.
