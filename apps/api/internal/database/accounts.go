package database

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
)

func (s *Store) Credentials(ctx context.Context, email string) (User, string, error) {
	var result User
	var passwordHash string
	err := s.pool.QueryRow(ctx, `
		SELECT u.id, u.name, u.email, u.email_verified, u.image, u.created_at, u.updated_at, a.password
		FROM "user" u
		JOIN account a ON a.user_id = u.id AND a.provider_id = 'credential'
		WHERE u.email = $1
	`, email).Scan(
		&result.ID,
		&result.Name,
		&result.Email,
		&result.EmailVerified,
		&result.Image,
		&result.CreatedAt,
		&result.UpdatedAt,
		&passwordHash,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return User{}, "", ErrNotFound
	}
	return result, passwordHash, err
}
