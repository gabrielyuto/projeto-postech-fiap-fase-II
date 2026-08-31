# evaluation-service-main
# =========================================================
# Etapa 1: Build
# =========================================================
FROM golang:1.21.13-alpine3.20 AS builder

WORKDIR /app

COPY go.mod go.sum ./
COPY . .

RUN go mod download && \
    CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o evaluation-service .

# =========================================================
# Etapa 2: Runtime
# =========================================================
FROM alpine:3.20.7

WORKDIR /app

RUN apk add --no-cache ca-certificates && \
    addgroup -g 1000 appuser && \
    adduser -D -u 1000 -G appuser appuser

COPY --from=builder /app/evaluation-service .

USER appuser

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:8004/health || exit 1

CMD ["./evaluation-service"]