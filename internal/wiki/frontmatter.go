package wiki

import (
	"bytes"
	"strings"

	"github.com/adrg/frontmatter"
)

type PageMetadata struct {
	Title string      `yaml:"title"`
	Tags  interface{} `yaml:"tags"`
}

// ParsedPage holds the metadata and body of a markdown file.
type ParsedPage struct {
	Title   string
	Tags    []string
	Body    string
	Snippet string
}

// ParseMarkdown extracts frontmatter and body from markdown content.
func ParseMarkdown(content []byte, fallbackTitle string) ParsedPage {
	var meta PageMetadata
	bodyBytes, err := frontmatter.Parse(bytes.NewReader(content), &meta)
	if err != nil {
		// If frontmatter parsing fails, treat the whole content as body
		bodyBytes = content
	}

	body := string(bodyBytes)
	title := strings.TrimSpace(meta.Title)
	if title == "" {
		title = extractTitleFromBody(body, fallbackTitle)
	}

	tags := normalizeTags(meta.Tags)
	snippet := makeSnippet(body, 300)

	return ParsedPage{
		Title:   title,
		Tags:    tags,
		Body:    body,
		Snippet: snippet,
	}
}

func extractTitleFromBody(body, fallback string) string {
	lines := strings.Split(body, "\n")
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "# ") {
			return strings.TrimSpace(strings.TrimPrefix(trimmed, "# "))
		}
	}
	return fallback
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
				trimmed := strings.TrimSpace(s)
				if trimmed != "" {
					tags = append(tags, trimmed)
				}
			}
		}
	case []string:
		for _, s := range v {
			trimmed := strings.TrimSpace(s)
			if trimmed != "" {
				tags = append(tags, trimmed)
			}
		}
	case string:
		for _, part := range strings.Split(v, ",") {
			trimmed := strings.TrimSpace(part)
			if trimmed != "" {
				tags = append(tags, trimmed)
			}
		}
	}
	return tags
}

func makeSnippet(text string, maxLen int) string {
	cleaned := strings.TrimSpace(text)
	// Collapse multiple whitespaces/newlines for clean snippet preview
	cleaned = strings.Join(strings.Fields(cleaned), " ")
	runes := []rune(cleaned)
	if len(runes) <= maxLen {
		return string(runes)
	}
	return string(runes[:maxLen]) + "..."
}
