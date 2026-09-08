package server

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"wiki-mcp/internal/config"
	"wiki-mcp/internal/git"
	"wiki-mcp/internal/wiki"
)

func TestHTTPServerHealthAndAuth(t *testing.T) {
	tempDir := t.TempDir()
	_ = os.WriteFile(tempDir+"/_ORIENTATION.md", []byte("# Dev Wiki"), 0644)

	cfg := &config.Config{
		WikiDir:       tempDir,
		AuthToken:     "secret-bearer-token",
		WebhookSecret: "webhook-secret-456",
		SyncCron:      "*/10 * * * *",
	}

	w, err := wiki.New(tempDir)
	if err != nil {
		t.Fatalf("failed to init wiki: %v", err)
	}

	syncer := git.NewSyncer(tempDir)
	mcpSrv := NewMCPServer(w)
	srv := NewHTTPServer(cfg, syncer, mcpSrv)
	handler := srv.Handler()

	// 1. Health check should bypass auth
	req := httptest.NewRequest("GET", "/health", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 OK for /health, got %d", rec.Code)
	}

	var healthRes map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &healthRes); err != nil {
		t.Fatalf("failed to parse /health JSON: %v", err)
	}
	if healthRes["status"] != "healthy" {
		t.Errorf("expected status 'healthy', got %v", healthRes["status"])
	}

	syncInfo, ok := healthRes["sync"].(map[string]any)
	if !ok {
		t.Fatalf("expected 'sync' object in health response")
	}
	if syncInfo["cron_enabled"] != true {
		t.Errorf("expected cron_enabled true, got %v", syncInfo["cron_enabled"])
	}

	// 2. /mcp without Bearer token should fail with 401
	req = httptest.NewRequest("POST", "/mcp", strings.NewReader(`{}`))
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 Unauthorized for /mcp without token, got %d", rec.Code)
	}

	// 3. /mcp with wrong Bearer token should fail with 401
	req = httptest.NewRequest("POST", "/mcp", strings.NewReader(`{}`))
	req.Header.Set("Authorization", "Bearer wrong-token")
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 for wrong token, got %d", rec.Code)
	}

	// 4. Webhook with invalid signature should return 401
	req = httptest.NewRequest("POST", "/webhook", strings.NewReader(`{"ref":"refs/heads/main"}`))
	req.Header.Set("X-Hub-Signature-256", "sha256=invalid")
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 for invalid webhook signature, got %d", rec.Code)
	}

	// 5. Webhook with valid signature should bypass Bearer auth and reach git pull
	payload := `{"ref":"refs/heads/main"}`
	mac := hmac.New(sha256.New, []byte("webhook-secret-456"))
	mac.Write([]byte(payload))
	validSig := "sha256=" + hex.EncodeToString(mac.Sum(nil))

	req = httptest.NewRequest("POST", "/webhook", strings.NewReader(payload))
	req.Header.Set("X-Hub-Signature-256", validSig)
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	// Since tempDir is not a real git repo with an upstream remote, pull will return error (500)
	// which verifies that authentication passed and reached the pull step!
	if rec.Code != http.StatusInternalServerError && rec.Code != http.StatusOK {
		t.Fatalf("expected webhook execution (500 in non-repo or 200 in repo), got %d", rec.Code)
	}
}
