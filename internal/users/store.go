package users

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"time"

	"github.com/cbaguilar/svwatergo/internal/database"
	"github.com/jmoiron/sqlx"
)

const (
	RoleAdmin     = 0
	RoleLabMember = 1
	RolePublic    = 2
)

type Store struct {
	DB     *sqlx.DB
	Driver string
}

type User struct {
	ID        int64     `json:"id"`
	Email     string    `json:"email"`
	Role      int       `json:"role"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type userRow struct {
	ID        int64     `db:"id"`
	Email     string    `db:"email"`
	Role      int       `db:"role"`
	CreatedAt time.Time `db:"created_at"`
	UpdatedAt time.Time `db:"updated_at"`
}

func NewStore(client *database.SQLXClient) *Store {
	if client == nil {
		return nil
	}
	return &Store{
		DB:     client.DB,
		Driver: client.Driver,
	}
}

func (s *Store) EnsureSchema(ctx context.Context) error {
	if s == nil {
		return nil
	}

	ddl := `CREATE TABLE IF NOT EXISTS users (
		id BIGSERIAL PRIMARY KEY,
		email TEXT NOT NULL UNIQUE,
		role INTEGER NOT NULL CHECK (role IN (0, 1, 2)),
		created_at TIMESTAMPTZ NOT NULL,
		updated_at TIMESTAMPTZ NOT NULL
	)`
	if s.Driver != "postgres" {
		ddl = `CREATE TABLE IF NOT EXISTS users (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			email TEXT NOT NULL UNIQUE,
			role INTEGER NOT NULL CHECK (role IN (0, 1, 2)),
			created_at TIMESTAMP NOT NULL,
			updated_at TIMESTAMP NOT NULL
		)`
	}
	if _, err := s.DB.ExecContext(ctx, ddl); err != nil {
		return fmt.Errorf("create users table: %w", err)
	}
	if _, err := s.DB.ExecContext(ctx, "CREATE INDEX IF NOT EXISTS users_role_idx ON users(role)"); err != nil {
		return fmt.Errorf("create users_role_idx: %w", err)
	}
	return nil
}

func NormalizeEmail(email string) string {
	return strings.ToLower(strings.TrimSpace(email))
}

func IsValidRole(role int) bool {
	return role == RoleAdmin || role == RoleLabMember || role == RolePublic
}

func (s *Store) ListUsers(ctx context.Context) ([]User, error) {
	if s == nil {
		return nil, fmt.Errorf("store not configured")
	}
	rows := []userRow{}
	if err := s.DB.SelectContext(ctx, &rows, `SELECT id, email, role, created_at, updated_at FROM users ORDER BY role ASC, email ASC`); err != nil {
		return nil, fmt.Errorf("list users: %w", err)
	}
	out := make([]User, 0, len(rows))
	for _, row := range rows {
		out = append(out, toUser(row))
	}
	return out, nil
}

func (s *Store) CreateUser(ctx context.Context, email string, role int) (User, error) {
	if s == nil {
		return User{}, fmt.Errorf("store not configured")
	}
	norm := NormalizeEmail(email)
	if norm == "" {
		return User{}, fmt.Errorf("email is required")
	}
	if !IsValidRole(role) {
		return User{}, fmt.Errorf("invalid role")
	}
	now := time.Now().UTC()

	args := map[string]any{
		"email":      norm,
		"role":       role,
		"created_at": now,
		"updated_at": now,
	}
	query := `INSERT INTO users(email, role, created_at, updated_at) VALUES (:email, :role, :created_at, :updated_at)`
	if s.Driver == "postgres" {
		query += ` RETURNING id, email, role, created_at, updated_at`
		rows, err := s.DB.NamedQueryContext(ctx, query, args)
		if err != nil {
			return User{}, fmt.Errorf("create user: %w", err)
		}
		defer rows.Close()
		if !rows.Next() {
			return User{}, fmt.Errorf("create user: no row returned")
		}
		var row userRow
		if err := rows.StructScan(&row); err != nil {
			return User{}, fmt.Errorf("create user: %w", err)
		}
		return toUser(row), nil
	}
	res, err := s.DB.NamedExecContext(ctx, query, args)
	if err != nil {
		return User{}, fmt.Errorf("create user: %w", err)
	}
	id, err := res.LastInsertId()
	if err != nil {
		return User{}, fmt.Errorf("create user: %w", err)
	}
	return s.GetUserByID(ctx, id)
}

func (s *Store) UpdateUser(ctx context.Context, id int64, email string, role int) (User, error) {
	if s == nil {
		return User{}, fmt.Errorf("store not configured")
	}
	if id <= 0 {
		return User{}, fmt.Errorf("invalid id")
	}
	norm := NormalizeEmail(email)
	if norm == "" {
		return User{}, fmt.Errorf("email is required")
	}
	if !IsValidRole(role) {
		return User{}, fmt.Errorf("invalid role")
	}
	now := time.Now().UTC()
	args := map[string]any{
		"id":         id,
		"email":      norm,
		"role":       role,
		"updated_at": now,
	}
	res, err := s.DB.NamedExecContext(ctx, `UPDATE users SET email = :email, role = :role, updated_at = :updated_at WHERE id = :id`, args)
	if err != nil {
		return User{}, fmt.Errorf("update user: %w", err)
	}
	affected, err := res.RowsAffected()
	if err != nil {
		return User{}, fmt.Errorf("update user: %w", err)
	}
	if affected == 0 {
		return User{}, sql.ErrNoRows
	}
	return s.GetUserByID(ctx, id)
}

func (s *Store) DeleteUser(ctx context.Context, id int64) error {
	if s == nil {
		return fmt.Errorf("store not configured")
	}
	if id <= 0 {
		return fmt.Errorf("invalid id")
	}
	res, err := s.DB.ExecContext(ctx, `DELETE FROM users WHERE id = ?`, id)
	if err != nil && s.Driver == "postgres" {
		res, err = s.DB.ExecContext(ctx, `DELETE FROM users WHERE id = $1`, id)
	}
	if err != nil {
		return fmt.Errorf("delete user: %w", err)
	}
	affected, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("delete user: %w", err)
	}
	if affected == 0 {
		return sql.ErrNoRows
	}
	return nil
}

func (s *Store) GetUserByID(ctx context.Context, id int64) (User, error) {
	if s == nil {
		return User{}, fmt.Errorf("store not configured")
	}
	row := userRow{}
	query := `SELECT id, email, role, created_at, updated_at FROM users WHERE id = ?`
	if s.Driver == "postgres" {
		query = `SELECT id, email, role, created_at, updated_at FROM users WHERE id = $1`
	}
	if err := s.DB.GetContext(ctx, &row, query, id); err != nil {
		return User{}, err
	}
	return toUser(row), nil
}

func (s *Store) IsAllowedEmail(ctx context.Context, email string) (bool, error) {
	if s == nil {
		return false, nil
	}
	norm := NormalizeEmail(email)
	if norm == "" {
		return false, nil
	}
	var n int
	query := `SELECT COUNT(1) FROM users WHERE email = ?`
	if s.Driver == "postgres" {
		query = `SELECT COUNT(1) FROM users WHERE email = $1`
	}
	if err := s.DB.GetContext(ctx, &n, query, norm); err != nil {
		return false, fmt.Errorf("lookup user by email: %w", err)
	}
	return n > 0, nil
}

func (s *Store) IsAdminEmail(ctx context.Context, email string) (bool, error) {
	if s == nil {
		return false, nil
	}
	norm := NormalizeEmail(email)
	if norm == "" {
		return false, nil
	}
	var n int
	query := `SELECT COUNT(1) FROM users WHERE email = ? AND role = ?`
	args := []any{norm, RoleAdmin}
	if s.Driver == "postgres" {
		query = `SELECT COUNT(1) FROM users WHERE email = $1 AND role = $2`
	}
	if err := s.DB.GetContext(ctx, &n, query, args...); err != nil {
		return false, fmt.Errorf("lookup admin by email: %w", err)
	}
	return n > 0, nil
}

func (s *Store) HasUsers(ctx context.Context) (bool, error) {
	if s == nil {
		return false, nil
	}
	var n int
	if err := s.DB.GetContext(ctx, &n, `SELECT COUNT(1) FROM users`); err != nil {
		return false, fmt.Errorf("count users: %w", err)
	}
	return n > 0, nil
}

func (s *Store) UpsertUserByEmail(ctx context.Context, email string, role int) error {
	if s == nil {
		return fmt.Errorf("store not configured")
	}
	norm := NormalizeEmail(email)
	if norm == "" {
		return nil
	}
	if !IsValidRole(role) {
		return fmt.Errorf("invalid role")
	}
	now := time.Now().UTC()
	args := map[string]any{
		"email":      norm,
		"role":       role,
		"created_at": now,
		"updated_at": now,
	}
	query := `INSERT INTO users(email, role, created_at, updated_at)
		VALUES (:email, :role, :created_at, :updated_at)
		ON CONFLICT (email) DO UPDATE SET
			role = CASE
				WHEN users.role = 0 OR EXCLUDED.role = 0 THEN 0
				ELSE EXCLUDED.role
			END,
			updated_at = EXCLUDED.updated_at`
	_, err := s.DB.NamedExecContext(ctx, query, args)
	if err != nil {
		return fmt.Errorf("upsert user: %w", err)
	}
	return nil
}

func toUser(row userRow) User {
	return User{
		ID:        row.ID,
		Email:     row.Email,
		Role:      row.Role,
		CreatedAt: row.CreatedAt.UTC(),
		UpdatedAt: row.UpdatedAt.UTC(),
	}
}
