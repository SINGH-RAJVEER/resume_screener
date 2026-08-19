# JWT Authentication

The API authenticates email/password users with stateless HS256 JSON Web Tokens. Passwords are hashed with bcrypt and JWTs contain the user ID in the standard `sub` claim. Tokens also include `iss`, `iat`, and `exp` claims.

## Configuration

- `JWT_SECRET` is required and must contain at least 32 characters. Use a cryptographically random, environment-specific value in production.
- `JWT_TTL` controls token lifetime as a Go duration and defaults to `168h`.

Changing `JWT_SECRET` invalidates every token signed with the previous secret.

## Sign In And Registration

`POST /api/auth/sign-in/email` and `POST /api/auth/sign-up/email` return this shape after successful authentication:

```json
{
    "user": {
        "id": "user-id",
        "name": "Ada",
        "email": "ada@example.com"
    },
    "token": "eyJ...",
    "tokenType": "Bearer",
    "expiresAt": "2026-08-06T12:00:00Z"
}
```

The web client stores the token in `localStorage`. Protected API requests must send it in the header:

```http
Authorization: Bearer eyJ...
```

`GET /api/auth/session` returns `{ "user": ... }` for a valid token and `null` otherwise. `GET /api/me` returns the current user or HTTP 401.

## Sign Out And Revocation

JWTs are stateless, so `POST /api/auth/sign-out` does not invalidate a token on the server. The web client signs out by deleting its local token. A stolen token remains valid until `exp`; rotate `JWT_SECRET` to invalidate all active tokens immediately.
