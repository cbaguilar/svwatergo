FROM golang:1.25-bookworm AS build

WORKDIR /src

RUN apt-get update \
  && apt-get install -y --no-install-recommends gcc libc6-dev libsqlite3-dev ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=1 GOOS=linux go build -o /out/svwatergo ./cmd/server

FROM debian:bookworm-slim

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates sqlite3 libsqlite3-0 curl \
  && rm -rf /var/lib/apt/lists/*

COPY --from=build /out/svwatergo /usr/local/bin/svwatergo
COPY config/sites ./config/sites

ENV APP_PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/health || exit 1

CMD ["svwatergo"]
