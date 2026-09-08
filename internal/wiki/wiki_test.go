package wiki

import (
	"os"
	"path/filepath"
	"testing"
)

func TestWikiOperations(t *testing.T) {
	tempDir := t.TempDir()

	// 1. Setup orientation files
	schemaContent := "# Dev Wiki Schema\nGuidelines here."
	_ = os.WriteFile(filepath.Join(tempDir, "SCHEMA.md"), []byte(schemaContent), 0644)

	indexContent := "# Dev Wiki Index\nIndex entries."
	_ = os.WriteFile(filepath.Join(tempDir, "index.md"), []byte(indexContent), 0644)

	logContent := "2026-09-01: init\n2026-09-02: updated auth"
	_ = os.WriteFile(filepath.Join(tempDir, "log.md"), []byte(logContent), 0644)

	// Setup concepts/ folder
	conceptsDir := filepath.Join(tempDir, "concepts")
	_ = os.Mkdir(conceptsDir, 0755)

	pageContent := `---
title: Auth Service
tags: [security, microservices]
---
# Authentication Guide
Details about JWT and OAuth.`
	_ = os.WriteFile(filepath.Join(conceptsDir, "auth.md"), []byte(pageContent), 0644)

	w, err := New(tempDir)
	if err != nil {
		t.Fatalf("failed to init wiki: %v", err)
	}

	// 2. Test ReadOrientation
	orientation, err := w.ReadOrientation()
	if err != nil {
		t.Fatalf("ReadOrientation error: %v", err)
	}
	if orientation.Schema != schemaContent {
		t.Errorf("expected schema %q, got %q", schemaContent, orientation.Schema)
	}
	if orientation.Index != indexContent {
		t.Errorf("expected index %q, got %q", indexContent, orientation.Index)
	}

	// 3. Test GetPage with direct path
	page, err := w.GetPage("concepts/auth.md")
	if err != nil {
		t.Fatalf("GetPage error: %v", err)
	}
	if page.Path != "concepts/auth.md" {
		t.Errorf("expected path 'concepts/auth.md', got %q", page.Path)
	}

	// 4. Test GetPage with simple slug
	pageBySlug, err := w.GetPage("auth")
	if err != nil {
		t.Fatalf("GetPage by slug error: %v", err)
	}
	if pageBySlug.Path != "concepts/auth.md" {
		t.Errorf("expected slug resolution to 'concepts/auth.md', got %q", pageBySlug.Path)
	}

	// 5. Test SearchWiki with Tag Filter
	results, err := w.SearchWiki("", "security")
	if err != nil {
		t.Fatalf("SearchWiki error: %v", err)
	}
	if len(results) != 1 {
		t.Fatalf("expected 1 result for tag 'security', got %d", len(results))
	}
	if results[0].Title != "Auth Service" {
		t.Errorf("expected title 'Auth Service', got %q", results[0].Title)
	}

	// 6. Test SearchWiki with Keyword Query
	results, err = w.SearchWiki("OAuth", "")
	if err != nil {
		t.Fatalf("SearchWiki query error: %v", err)
	}
	if len(results) != 1 {
		t.Fatalf("expected 1 result for query 'OAuth', got %d", len(results))
	}
}
