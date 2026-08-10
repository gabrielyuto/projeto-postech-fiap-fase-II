# auth-service-main
# =========================================================
# Etapa 1: Build
# =========================================================
FROM golang:1.21-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN go mod tidy

RUN CGO_ENABLED=0 GOOS=linux go build -o auth-service .

# =========================================================
# Etapa 2: Runtime
# =========================================================
FROM alpine:3.20

WORKDIR /app

RUN apk add --no-cache ca-certificates && \
    addgroup -g 1000 appuser && \
    adduser -D -u 1000 -G appuser appuser

COPY --from=builder /app/auth-service .

USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:8001/health || exit 1

CMD ["./auth-service"]