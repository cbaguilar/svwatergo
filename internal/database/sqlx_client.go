package database

import (
	"github.com/jmoiron/sqlx"
	_ "github.com/lib/pq"
)

type SQLXClient struct {
	DB *sqlx.DB
}

func NewSQLXClient(conn string) (*SQLXClient, error) {
	db, err := sqlx.Connect("postgres", conn)
	if err != nil {
		return nil, err
	}
	db.Exec("SET TIME ZONE 'UTC'")
	return &SQLXClient{DB: db}, nil
}
