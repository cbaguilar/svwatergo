.PHONY: run test build

run:
	go run cmd/server/main.go

test:
	go test ./...

build:
	go build -o bin/server cmd/server/main.go