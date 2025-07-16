package database

import (
	"database/sql"
	"log"

	_ "github.com/lib/pq"
)

func ConnectDB(connectionString string) (*sql.DB, error) {
	db, err := sql.Open("postgres", connectionString)
	if err != nil {
		log.Fatal("Failed to connect to the database:", err)
		return nil, err
	}

	if err := db.Ping(); err != nil {
		log.Fatal("Failed to ping the database:", err)
		return nil, err
	}

	return db, nil
}
