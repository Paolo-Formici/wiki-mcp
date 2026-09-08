BINARY_NAME=dev-mcp
BUILD_DIR=bin
GO_FILES=$(shell find . -name '*.go' -not -path "./vendor/*")

.PHONY: all build test clean run-stdio run-serve docker-build

all: build

build:
	@mkdir -p $(BUILD_DIR)
	go build -ldflags="-s -w" -o $(BUILD_DIR)/$(BINARY_NAME) cmd/dev-mcp/main.go

test:
	go test -v -race ./...

clean:
	rm -rf $(BUILD_DIR)

run-stdio: build
	./$(BUILD_DIR)/$(BINARY_NAME) stdio --wiki-dir ../dev-wiki

run-serve: build
	./$(BUILD_DIR)/$(BINARY_NAME) serve --wiki-dir ../dev-wiki --port 8080

docker-build:
	docker build -t dev-mcp:latest .
