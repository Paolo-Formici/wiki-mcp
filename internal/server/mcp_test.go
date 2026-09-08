package server

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"dev-mcp/internal/wiki"

	"github.com/mark3labs/mcp-go/mcp"
)

func TestMCPServerWikiHelpPrompt(t *testing.T) {
	tempDir := t.TempDir()

	w, err := wiki.New(tempDir)
	if err != nil {
		t.Fatalf("failed to init wiki: %v", err)
	}

	s := NewMCPServer(w)

	// 1. Verify wiki-help prompt is registered
	prompts := s.ListPrompts()
	serverPrompt, ok := prompts["wiki-help"]
	if !ok {
		t.Fatalf("expected prompt 'wiki-help' to be registered, found: %v", prompts)
	}
	if serverPrompt.Prompt.Description != "Quick reference guide for navigating and using the team dev-wiki and engineering tools" {
		t.Errorf("unexpected description: %s", serverPrompt.Prompt.Description)
	}

	// 2. Test invoking the prompt with default fallback
	ctx := context.Background()
	req := mcp.GetPromptRequest{}
	req.Params.Name = "wiki-help"

	res, err := serverPrompt.Handler(ctx, req)
	if err != nil {
		t.Fatalf("prompt handler returned error: %v", err)
	}
	if len(res.Messages) != 1 {
		t.Fatalf("expected 1 prompt message, got %d", len(res.Messages))
	}
	msg := res.Messages[0]
	if msg.Role != mcp.RoleUser {
		t.Errorf("expected role 'user', got %q", msg.Role)
	}
	textContent, ok := msg.Content.(mcp.TextContent)
	if !ok {
		t.Fatalf("expected TextContent, got %T", msg.Content)
	}
	if !strings.Contains(textContent.Text, "Dev Wiki & Engineering Tools Quick Reference") {
		t.Errorf("expected default help text in prompt, got: %s", textContent.Text)
	}

	// 3. Test invoking the prompt with custom HELP.md present
	customHelp := "# Acme Team Custom Help\nUse Slack #eng-help."
	if err := os.WriteFile(filepath.Join(tempDir, "HELP.md"), []byte(customHelp), 0644); err != nil {
		t.Fatalf("failed to write HELP.md: %v", err)
	}

	resCustom, err := serverPrompt.Handler(ctx, req)
	if err != nil {
		t.Fatalf("prompt handler returned error on custom HELP.md: %v", err)
	}
	msgCustom := resCustom.Messages[0]
	textContentCustom := msgCustom.Content.(mcp.TextContent)
	if textContentCustom.Text != customHelp {
		t.Errorf("expected custom help %q, got %q", customHelp, textContentCustom.Text)
	}
}
