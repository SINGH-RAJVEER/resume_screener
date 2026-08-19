package auth

import (
	"context"
	"template/api/internal/database"
)

type Store interface {
	Register(context.Context, string, string, string) (database.User, error)
	Credentials(context.Context, string) (database.User, string, error)
	User(context.Context, string) (database.User, error)
}
