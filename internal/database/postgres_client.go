package database

import (
	"database/sql"
	"log"

	_ "github.com/lib/pq"
)

type PostgresClient struct {
	DB *sql.DB
}

func NewPostgresClient(connectionString string) (*PostgresClient, error) {
	db, err := sql.Open("postgres", connectionString)
	if err != nil {
		log.Printf("Failed to connect to the database: %v", err)
		return nil, err
	}

	if err := db.Ping(); err != nil {
		log.Printf("Failed to ping the database: %v", err)
		return nil, err
	}

	return &PostgresClient{DB: db}, nil
}

func (p *PostgresClient) Exec(query string, args ...any) (sql.Result, error) {
	return p.DB.Exec(query, args...)
}

func (p *PostgresClient) QueryRow(query string, args ...any) *sql.Row {
	return p.DB.QueryRow(query, args...)
}

func (p *PostgresClient) Query(query string, args ...any) (*sql.Rows, error) {
	return p.DB.Query(query, args...)
}
