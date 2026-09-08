package server

import (
	"context"
	"encoding/json"
	"fmt"

	"dev-mcp/internal/wiki"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
)

// NewMCPServer creates and registers all tools for dev-mcp matching the Python API.
func NewMCPServer(w *wiki.Wiki) *server.MCPServer {
	s := server.NewMCPServer("dev-mcp", "0.2.0")

	// 1. read_orientation
	s.AddTool(mcp.NewTool("read_orientation",
		mcp.WithDescription("Reads SCHEMA.md, index.md, and the last 30 lines of log.md in a single call for instant agent orientation"),
		mcp.WithReadOnlyHintAnnotation(true),
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		res, err := w.ReadOrientation()
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}

		jsonBytes, err := json.MarshalIndent(res, "", "  ")
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("error marshaling orientation: %v", err)), nil
		}
		return mcp.NewToolResultText(string(jsonBytes)), nil
	})

	// 2. get_page
	s.AddTool(mcp.NewTool("get_page",
		mcp.WithDescription("Returns the content and parsed YAML frontmatter of any page. Accepts direct paths (e.g. 'concepts/transformer.md') or simple slugs ('transformer')"),
		mcp.WithString("slug_or_path", mcp.Required(), mcp.Description("Direct path or slug of the page to read")),
		mcp.WithReadOnlyHintAnnotation(true),
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		slugOrPath, err := req.RequireString("slug_or_path")
		if err != nil {
			// Also check "rel_path" for backwards compatibility
			slugOrPath = req.GetString("rel_path", "")
			if slugOrPath == "" {
				return mcp.NewToolResultError("missing required parameter: slug_or_path"), nil
			}
		}

		res, err := w.GetPage(slugOrPath)
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}

		jsonBytes, err := json.MarshalIndent(res, "", "  ")
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("error marshaling page result: %v", err)), nil
		}
		return mcp.NewToolResultText(string(jsonBytes)), nil
	})

	// 3. search_wiki
	s.AddTool(mcp.NewTool("search_wiki",
		mcp.WithDescription("Searches content and frontmatter across concepts/, entities/, comparisons/, and queries/. Optionally filters results by taxonomy tag"),
		mcp.WithString("query", mcp.Description("Keyword to search in title, tags, or content")),
		mcp.WithString("tag", mcp.Description("Taxonomy tag to filter by")),
		mcp.WithReadOnlyHintAnnotation(true),
	), func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		query := req.GetString("query", "")
		tag := req.GetString("tag", "")

		results, err := w.SearchWiki(query, tag)
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}

		jsonBytes, err := json.MarshalIndent(results, "", "  ")
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("error marshaling search results: %v", err)), nil
		}
		return mcp.NewToolResultText(string(jsonBytes)), nil
	})

	// 4. Prompt: wiki-help
	s.AddPrompt(mcp.NewPrompt("wiki-help",
		mcp.WithPromptDescription("Quick reference guide for navigating and using the team dev-wiki and engineering tools"),
	), func(ctx context.Context, req mcp.GetPromptRequest) (*mcp.GetPromptResult, error) {
		helpText := w.GetHelp()
		return mcp.NewGetPromptResult(
			"Team Dev-Wiki Quick Reference Guide",
			[]mcp.PromptMessage{
				mcp.NewPromptMessage(mcp.RoleUser, mcp.NewTextContent(helpText)),
			},
		), nil
	})

	return s
}
