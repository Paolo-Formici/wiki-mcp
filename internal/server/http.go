package server

import (
	"encoding/json"
	"io"
	"log"
	"net/http"
	"time"

	"dev-mcp/internal/config"
	"dev-mcp/internal/git"

	mcpserver "github.com/mark3labs/mcp-go/server"
)

type HTTPServer struct {
	cfg       *config.Config
	syncer    *git.Syncer
	mcpServer *mcpserver.MCPServer
}

func NewHTTPServer(cfg *config.Config, syncer *git.Syncer, mcpServer *mcpserver.MCPServer) *HTTPServer {
	return &HTTPServer{
		cfg:       cfg,
		syncer:    syncer,
		mcpServer: mcpServer,
	}
}

func (s *HTTPServer) Handler() http.Handler {
	mux := http.NewServeMux()

	// 1. Health probe
	mux.HandleFunc("GET /health", s.handleHealth)

	// 2. Inbound Git webhook (GitHub / GitLab)
	mux.HandleFunc("POST /webhook", s.handleWebhook)

	// 3. MCP Streamable HTTP transport
	streamableServer := mcpserver.NewStreamableHTTPServer(
		s.mcpServer,
		mcpserver.WithDisableLocalhostProtection(true),
	)
	mux.Handle("/mcp", streamableServer)
	mux.Handle("/mcp/", streamableServer)

	// Wrap everything with Bearer token authentication
	return TokenAuthMiddleware(s.cfg.AuthToken, mux)
}

func (s *HTTPServer) handleHealth(w http.ResponseWriter, r *http.Request) {
	commit := git.GetCurrentCommit(s.cfg.WikiDir)
	meta := s.syncer.GetMetadata()

	syncMode := "webhook"
	if s.cfg.SyncCron != "" {
		syncMode = "hybrid"
	}

	res := map[string]any{
		"status": "healthy",
		"wiki":   s.cfg.WikiDir,
		"commit": commit,
		"sync": map[string]any{
			"mode":              syncMode,
			"cron_expression":   s.cfg.SyncCron,
			"cron_enabled":      s.cfg.SyncCron != "",
			"last_sync_at":      meta.LastSyncAt,
			"last_sync_trigger": meta.LastSyncTrigger,
			"last_sync_status":  meta.LastSyncStatus,
			"last_sync_commit":  meta.LastSyncCommit,
			"last_sync_error":   meta.LastSyncError,
		},
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(res)
}

func (s *HTTPServer) handleWebhook(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		writeJSONError(w, http.StatusBadRequest, "failed to read request body")
		return
	}

	if s.cfg.WebhookSecret != "" {
		ghSig := r.Header.Get("X-Hub-Signature-256")
		glToken := r.Header.Get("X-Gitlab-Token")

		validGH := git.VerifyGitHubSignature(body, ghSig, s.cfg.WebhookSecret)
		validGL := git.VerifyGitLabToken(glToken, s.cfg.WebhookSecret)

		if !validGH && !validGL {
			log.Println("[webhook] Authentication failed: invalid signature or token")
			writeJSONError(w, http.StatusUnauthorized, "Invalid webhook signature")
			return
		}
	}

	start := time.Now()
	success, commit, out := s.syncer.PullRepo("webhook")
	durationMs := float64(time.Since(start).Microseconds()) / 1000.0

	w.Header().Set("Content-Type", "application/json")
	if !success {
		w.WriteHeader(http.StatusInternalServerError)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"status": "error",
			"error":  out,
			"commit": commit,
		})
		return
	}

	_ = json.NewEncoder(w).Encode(map[string]any{
		"status":      "synced",
		"commit":      commit,
		"output":      out,
		"duration_ms": durationMs,
	})
}
