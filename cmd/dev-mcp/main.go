package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"dev-mcp/internal/config"
	"dev-mcp/internal/cron"
	"dev-mcp/internal/git"
	"dev-mcp/internal/server"
	"dev-mcp/internal/wiki"

	mcpserver "github.com/mark3labs/mcp-go/server"
	"github.com/spf13/cobra"
)

var (
	version = "0.2.0"
	cfg     = config.LoadFromEnv()
)

func main() {
	rootCmd := &cobra.Command{
		Use:     "dev-mcp",
		Short:   "Model Context Protocol server for Dev Wiki",
		Version: version,
	}

	rootCmd.PersistentFlags().StringVar(&cfg.WikiDir, "wiki-dir", cfg.WikiDir, "Path to wiki root directory")

	// 1. stdio command
	stdioCmd := &cobra.Command{
		Use:   "stdio",
		Short: "Run the MCP server over standard input/output (for local IDEs)",
		RunE: func(cmd *cobra.Command, args []string) error {
			w, err := wiki.New(cfg.WikiDir)
			if err != nil {
				return err
			}

			mcpSrv := server.NewMCPServer(w)
			stdioSrv := mcpserver.NewStdioServer(mcpSrv)
			return stdioSrv.Listen(cmd.Context(), os.Stdin, os.Stdout)
		},
	}

	// 2. serve command
	serveCmd := &cobra.Command{
		Use:   "serve",
		Short: "Run the remote HTTP/SSE server with webhooks and optional cron sync",
		RunE: func(cmd *cobra.Command, args []string) error {
			if cfg.RepoURL != "" {
				if err := git.EnsureGitRepo(cfg.WikiDir, cfg.RepoURL); err != nil {
					return fmt.Errorf("failed to ensure git repo: %w", err)
				}
			}

			w, err := wiki.New(cfg.WikiDir)
			if err != nil {
				return err
			}

			syncer := git.NewSyncer(cfg.WikiDir)
			mcpSrv := server.NewMCPServer(w)

			// Initialize cron scheduler if configured
			if cfg.SyncCron != "" {
				sched, err := cron.NewScheduler(syncer, cfg.SyncCron)
				if err != nil {
					return fmt.Errorf("invalid cron expression %q: %w", cfg.SyncCron, err)
				}
				sched.Start()
				defer sched.Stop()
				log.Printf("Cron git sync scheduled with expression: %s\n", cfg.SyncCron)
			}

			httpSrv := server.NewHTTPServer(cfg, syncer, mcpSrv)
			addr := fmt.Sprintf("%s:%d", cfg.Host, cfg.Port)
			serverInstance := &http.Server{
				Addr:    addr,
				Handler: httpSrv.Handler(),
			}

			// Graceful shutdown handling
			stopChan := make(chan os.Signal, 1)
			signal.Notify(stopChan, os.Interrupt, syscall.SIGTERM)

			go func() {
				log.Printf("Starting dev-mcp HTTP server on http://%s (wiki: %s)\n", addr, cfg.WikiDir)
				if err := serverInstance.ListenAndServe(); err != nil && err != http.ErrServerClosed {
					log.Fatalf("HTTP server error: %v", err)
				}
			}()

			<-stopChan
			log.Println("Shutting down server gracefully...")
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			return serverInstance.Shutdown(ctx)
		},
	}

	serveCmd.Flags().StringVar(&cfg.Host, "host", cfg.Host, "Host to bind")
	serveCmd.Flags().IntVar(&cfg.Port, "port", cfg.Port, "Port to listen on")
	serveCmd.Flags().StringVar(&cfg.AuthToken, "auth-token", cfg.AuthToken, "Bearer token for authentication")
	serveCmd.Flags().StringVar(&cfg.WebhookSecret, "webhook-secret", cfg.WebhookSecret, "Secret for HMAC webhook signature verification")
	serveCmd.Flags().StringVar(&cfg.SyncCron, "sync-cron", cfg.SyncCron, "Cron expression for periodic git pull")
	serveCmd.Flags().StringVar(&cfg.RepoURL, "repo-url", cfg.RepoURL, "Git repository URL to clone if missing")

	rootCmd.AddCommand(stdioCmd, serveCmd)

	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}
