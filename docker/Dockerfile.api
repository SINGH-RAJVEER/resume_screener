FROM golang:1.24-alpine AS builder
WORKDIR /src/apps/api

COPY apps/api/go.mod apps/api/go.sum ./
RUN go mod download

COPY apps/api/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /api ./cmd/api

FROM alpine:3.22 AS runner
RUN apk add --no-cache ca-certificates \
    && addgroup -S app \
    && adduser -S -G app app
USER app
COPY --from=builder /api /app/api

EXPOSE 8000

CMD ["/app/api"]
