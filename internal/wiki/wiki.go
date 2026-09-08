package wiki

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/adrg/frontmatter"
)

type Wiki struct {
	rootDir string
}

type OrientationResult struct {
	WikiPath          string `json:"wiki_path"`
	Schema            string `json:"schema"`
	Index             string `json:"index"`
	RecentActivityLog string `json:"recent_activity_log"`
}

type SearchResult struct {
	Path    string   `json:"path"`
	Title   string   `json:"title"`
	Tags    []string `json:"tags"`
	Snippet string   `json:"snippet"`
}

type PageResult struct {
	Path        string         `json:"path"`
	Frontmatter map[string]any `json:"frontmatter"`
	Content     string         `json:"content"`
}

// New initializes a Wiki instance pointing to rootDir.
func New(rootDir string) (*Wiki, error) {
	absPath, err := filepath.Abs(rootDir)
	if err != nil {
		return nil, fmt.Errorf("invalid wiki directory path: %w", err)
	}

	info, err := os.Stat(absPath)
	if err != nil {
		return nil, fmt.Errorf("wiki directory does not exist: %w", err)
	}
	if !info.IsDir() {
		return nil, fmt.Errorf("wiki path is not a directory: %s", absPath)
	}

	return &Wiki{rootDir: absPath}, nil
}

// ReadOrientation returns SCHEMA.md, index.md, and the last 30 lines of log.md.
func (w *Wiki) ReadOrientation() (*OrientationResult, error) {
	schemaText := "SCHEMA.md not found."
	if b, err := os.ReadFile(filepath.Join(w.rootDir, "SCHEMA.md")); err == nil {
		schemaText = string(b)
	}

	indexText := "index.md not found."
	if b, err := os.ReadFile(filepath.Join(w.rootDir, "index.md")); err == nil {
		indexText = string(b)
	}

	var recentLogs []string
	if b, err := os.ReadFile(filepath.Join(w.rootDir, "log.md")); err == nil {
		lines := strings.Split(string(b), "\n")
		start := len(lines) - 30
		if start < 0 {
			start = 0
		}
		recentLogs = lines[start:]
	}

	return &OrientationResult{
		WikiPath:          w.rootDir,
		Schema:            schemaText,
		Index:             indexText,
		RecentActivityLog: strings.Join(recentLogs, "\n"),
	}, nil
}

// isSafePath checks if targetPath is strictly inside baseDir.
func isSafePath(baseDir, targetPath string) bool {
	rel, err := filepath.Rel(baseDir, targetPath)
	if err != nil {
		return false
	}
	return !strings.HasPrefix(rel, "..") && !filepath.IsAbs(rel)
}

// ResolvePagePath finds a page either by direct path ("concepts/auth.md") or slug ("auth").
func (w *Wiki) ResolvePagePath(slugOrPath string) (string, error) {
	clean := strings.TrimSpace(slugOrPath)
	clean = strings.TrimSuffix(clean, ".md")

	// 1. Direct path check
	directPath := filepath.Join(w.rootDir, clean+".md")
	if info, err := os.Stat(directPath); err == nil && !info.IsDir() && isSafePath(w.rootDir, directPath) {
		return directPath, nil
	}

	// 2. Search across folders excluding hidden
	var matchedPath string
	targetFile := clean + ".md"
	if idx := strings.LastIndex(clean, "/"); idx != -1 {
		targetFile = clean[idx+1:] + ".md"
	}

	_ = filepath.WalkDir(w.rootDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			if strings.HasPrefix(d.Name(), ".") && path != w.rootDir {
				return filepath.SkipDir
			}
			return nil
		}

		if d.Name() == targetFile && isSafePath(w.rootDir, path) {
			matchedPath = path
			return filepath.SkipAll
		}
		return nil
	})

	if matchedPath != "" {
		return matchedPath, nil
	}

	return "", fmt.Errorf("page '%s' not found in wiki", slugOrPath)
}

// GetPage returns the frontmatter and content of any page.
func (w *Wiki) GetPage(slugOrPath string) (*PageResult, error) {
	filePath, err := w.ResolvePagePath(slugOrPath)
	if err != nil {
		return nil, err
	}

	content, err := os.ReadFile(filePath)
	if err != nil {
		return nil, err
	}

	meta := make(map[string]any)
	bodyBytes, err := frontmatter.Parse(bytes.NewReader(content), &meta)
	body := string(content)
	if err == nil {
		body = strings.TrimSpace(string(bodyBytes))
	}

	relPath, _ := filepath.Rel(w.rootDir, filePath)
	return &PageResult{
		Path:        filepath.ToSlash(relPath),
		Frontmatter: meta,
		Content:     body,
	}, nil
}

// SearchWiki searches concepts/, entities/, comparisons/, and queries/.
func (w *Wiki) SearchWiki(query string, tag string) ([]SearchResult, error) {
	var results []SearchResult

	queryLower := strings.ToLower(strings.TrimSpace(query))
	tagLower := strings.ToLower(strings.TrimSpace(tag))

	targetFolders := []string{"concepts", "entities", "comparisons", "queries"}

	for _, folderName := range targetFolders {
		folderPath := filepath.Join(w.rootDir, folderName)
		info, err := os.Stat(folderPath)
		if err != nil || !info.IsDir() {
			continue
		}

		entries, err := os.ReadDir(folderPath)
		if err != nil {
			continue
		}

		for _, entry := range entries {
			if entry.IsDir() || !strings.HasSuffix(strings.ToLower(entry.Name()), ".md") {
				continue
			}

			fullPath := filepath.Join(folderPath, entry.Name())
			content, err := os.ReadFile(fullPath)
			if err != nil {
				continue
			}

			meta := make(map[string]any)
			bodyBytes, _ := frontmatter.Parse(bytes.NewReader(content), &meta)
			body := string(bodyBytes)

			// Extract tags
			var tags []string
			if rawTags, ok := meta["tags"]; ok {
				tags = normalizeTags(rawTags)
			}

			// Tag filter check
			if tagLower != "" {
				tagMatched := false
				for _, t := range tags {
					if strings.ToLower(t) == tagLower {
						tagMatched = true
						break
					}
				}
				if !tagMatched {
					continue
				}
			}

			// Title check
			baseName := strings.TrimSuffix(entry.Name(), ".md")
			title := baseName
			if t, ok := meta["title"].(string); ok && strings.TrimSpace(t) != "" {
				title = t
			}

			// Query check
			if queryLower != "" {
				bodyMatch := strings.Contains(strings.ToLower(body), queryLower)
				titleMatch := strings.Contains(strings.ToLower(title), queryLower)
				tagMatch := false
				for _, t := range tags {
					if strings.Contains(strings.ToLower(t), queryLower) {
						tagMatch = true
						break
					}
				}

				if !bodyMatch && !titleMatch && !tagMatch {
					continue
				}
			}

			relPath, _ := filepath.Rel(w.rootDir, fullPath)
			results = append(results, SearchResult{
				Path:    filepath.ToSlash(relPath),
				Title:   title,
				Tags:    tags,
				Snippet: extractSnippet(body, query, 250),
			})
		}
	}

	return results, nil
}

func extractSnippet(text, query string, maxChars int) string {
	if maxChars <= 0 {
		maxChars = 250
	}
	textLower := strings.ToLower(text)
	queryLower := strings.ToLower(query)

	idx := -1
	if queryLower != "" {
		idx = strings.Index(textLower, queryLower)
	}

	if idx == -1 {
		cleaned := strings.TrimSpace(text)
		cleaned = strings.Join(strings.Fields(cleaned), " ")
		runes := []rune(cleaned)
		if len(runes) > maxChars {
			return string(runes[:maxChars]) + "..."
		}
		return string(runes)
	}

	halfWindow := maxChars / 2
	start := idx - halfWindow
	if start < 0 {
		start = 0
	}
	end := idx + len(query) + halfWindow
	runes := []rune(text)
	if end > len(runes) {
		end = len(runes)
	}

	snippet := strings.TrimSpace(string(runes[start:end]))
	snippet = strings.Join(strings.Fields(snippet), " ")

	prefix := ""
	suffix := ""
	if start > 0 {
		prefix = "..."
	}
	if end < len(runes) {
		suffix = "..."
	}

	return prefix + snippet + suffix
}

func normalizeTags(raw interface{}) []string {
	var tags []string
	if raw == nil {
		return tags
	}

	switch v := raw.(type) {
	case []interface{}:
		for _, item := range v {
			if s, ok := item.(string); ok {
				if trimmed := strings.TrimSpace(s); trimmed != "" {
					tags = append(tags, trimmed)
				}
			}
		}
	case []string:
		for _, s := range v {
			if trimmed := strings.TrimSpace(s); trimmed != "" {
				tags = append(tags, trimmed)
			}
		}
	case string:
		for _, part := range strings.Split(v, ",") {
			if trimmed := strings.TrimSpace(part); trimmed != "" {
				tags = append(tags, trimmed)
			}
		}
	}
	return tags
}

// GetHelp returns the content of HELP.md or help.md from the wiki root if it exists,
// or a comprehensive built-in quick reference card if not found.
func (w *Wiki) GetHelp() string {
	candidates := []string{"HELP.md", "help.md"}
	for _, name := range candidates {
		if b, err := os.ReadFile(filepath.Join(w.rootDir, name)); err == nil && len(strings.TrimSpace(string(b))) > 0 {
			return string(b)
		}
	}
	return DefaultHelp()
}

// DefaultHelp returns the built-in quick reference markdown when no custom HELP.md is present.
func DefaultHelp() string {
	return `# Dev Wiki & Engineering Tools Quick Reference

Welcome to the team knowledge base and engineering assistant.

### 📚 Knowledge Base Structure
This wiki is organized using the Karpathy LLM-wiki pattern across four curated layers:
- **` + "`concepts/`" + `**: Foundational architectural decisions, security standards, coding guidelines, and technical definitions.
- **` + "`entities/`" + `**: Services, internal components, repositories, databases, and third-party API integrations.
- **` + "`comparisons/`" + `**: Technology evaluations, architectural trade-offs (e.g., REST vs gRPC, Redis vs Memcached).
- **` + "`queries/`" + `**: Pre-computed answers to recurring cross-cutting engineering questions.

### 🛠️ Available MCP Tools
- **` + "`read_orientation()`" + `**: Reads SCHEMA.md, index.md, and recent changelogs in a single roundtrip. Call this first to orient yourself.
- **` + "`search_wiki(query, tag)`" + `**: Fast full-text and tag search across all curated pages.
- **` + "`get_page(slug_or_path)`" + `**: Reads any wiki page by relative path (e.g., ` + "`concepts/auth.md`" + `) or slug (e.g., ` + "`auth`" + `) with parsed frontmatter and markdown body.

### 💡 Tips for Developers & Agents
1. **Search before building**: Query existing concepts or entity pages before designing new architecture.
2. **Read-only integrity**: The wiki is read-only via MCP to prevent headless merge conflicts and ensure data integrity.
3. **Contributing**: Propose new documentation or edits via pull requests on the wiki Git repository.`
}
