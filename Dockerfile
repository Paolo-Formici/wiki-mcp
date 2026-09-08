# Build stage
FROM golang:1.24-alpine AS builder

WORKDIR /app

RUN apk add --no-cache git

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /bin/dev-mcp cmd/dev-mcp/main.go

# Final runtime stage
FROM alpine:3.20

RUN apk add --no-cache git ca-certificates curl

WORKDIR /app
COPY --from=builder /bin/dev-mcp /usr/local/bin/dev-mcp

ENV WIKI_DIR=/data/wiki
ENV HOST=0.0.0.0
ENV PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["dev-mcp"]
CMD ["serve"]
