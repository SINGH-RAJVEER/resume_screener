package database

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
)

func (s *Store) Register(
	ctx context.Context,
	name string,
	email string,
	passwordHash string,
) (User, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return User{}, err
	}
	defer tx.Rollback(ctx) // No-op after Commit.

	now := time.Now().UTC()
	newUser := User{
		ID:        randomID(),
		Name:      name,
		Email:     email,
		CreatedAt: now,
		UpdatedAt: now,
	}

	_, err = tx.Exec(ctx, `
		INSERT INTO "user" (id, name, email, email_verified, created_at, updated_at)
		VALUES ($1, $2, $3, FALSE, $4, $4)
	`, newUser.ID, newUser.Name, newUser.Email, now)
	if isUniqueViolation(err) {
		return User{}, ErrEmailUsed
	}
	if err != nil {
		return User{}, err
	}

	_, err = tx.Exec(ctx, `
		INSERT INTO account (id, account_id, provider_id, user_id, password, created_at, updated_at)
		VALUES ($1, $2, 'credential', $3, $4, $5, $5)
	`, randomID(), newUser.Email, newUser.ID, passwordHash, now)
	if err != nil {
		return User{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return User{}, err
	}
	return newUser, nil
}

func (s *Store) User(ctx context.Context, id string) (User, error) {
	var result User
	err := s.pool.QueryRow(ctx, `
		SELECT id, name, email, email_verified, image, created_at, updated_at
		FROM "user"
		WHERE id = $1
	`, id).Scan(&result.ID, &result.Name, &result.Email, &result.EmailVerified, &result.Image, &result.CreatedAt, &result.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return User{}, ErrNotFound
	}
	return result, err
}
