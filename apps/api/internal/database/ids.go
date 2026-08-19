package database

import (
	"crypto/rand"
	"encoding/base64"
	"fmt"
)

func randomID() string {
	id, err := randomToken(18)
	if err != nil {
		panic(fmt.Sprintf("generate random ID: %v", err))
	}
	return id
}

func randomToken(size int) (string, error) {
	value := make([]byte, size)
	if _, err := rand.Read(value); err != nil {
		return "", fmt.Errorf("read random bytes: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(value), nil
}
