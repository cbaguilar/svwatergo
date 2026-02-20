package database

import (
	"time"

	"github.com/jmoiron/sqlx"
	_ "github.com/lib/pq"
	_ "github.com/mattn/go-sqlite3"
)

type SQLXClient struct {
	DB     *sqlx.DB
	Driver string
}

func NewSQLXClient(driver string, conn string) (*SQLXClient, error) {
	db, err := sqlx.Connect(driver, conn)
	if err != nil {
		return nil, err
	}
	db = db.Unsafe()
	db.Exec("SET TIME ZONE 'UTC'")
	return &SQLXClient{DB: db, Driver: driver}, nil
}

func NewSQLiteClient(path string) (*SQLXClient, error) {
	dsn := path + "?_busy_timeout=5000&_journal_mode=WAL&_foreign_keys=on"

	db, err := sqlx.Open("sqlite3", dsn)
	if err != nil {
		return nil, err
	}

	db.SetMaxOpenConns(1) // SQLite is single file; 1 writer at a time
	db.SetConnMaxLifetime(30 * time.Minute)

	// Safety PRAGMAs (also set via DSN above)
	db.Exec("PRAGMA foreign_keys = ON")
	db.Exec("PRAGMA journal_mode = WAL")

	if err := db.Ping(); err != nil {
		return nil, err
	}
	db = db.Unsafe()
	return &SQLXClient{DB: db, Driver: "sqlite3"}, nil
}

func NewPostgresClient(conn string) (*SQLXClient, error) {
	db, err := sqlx.Open("postgres", conn)
	if err != nil {
		return nil, err
	}

	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(25)
	db.SetConnMaxLifetime(5 * time.Minute)
	if err := db.Ping(); err != nil {
		return nil, err
	}
	db = db.Unsafe()
	return &SQLXClient{DB: db, Driver: "postgres"}, nil
}
