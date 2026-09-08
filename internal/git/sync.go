package git

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"sync"
	"time"
)

type SyncMetadata struct {
	LastSyncAt      string `json:"last_sync_at"`
	LastSyncTrigger string `json:"last_sync_trigger"`
	LastSyncStatus  string `json:"last_sync_status"`
	LastSyncCommit  string `json:"last_sync_commit"`
	LastSyncError   string `json:"last_sync_error,omitempty"`
}

type Syncer struct {
	wikiDir  string
	mu       sync.RWMutex
	metadata SyncMetadata
}

func NewSyncer(wikiDir string) *Syncer {
	commit := GetCurrentCommit(wikiDir)
	return &Syncer{
		wikiDir: wikiDir,
		metadata: SyncMetadata{
			LastSyncStatus: "idle",
			LastSyncCommit: commit,
		},
	}
}

// EnsureGitRepo verifies that wikiDir is a git repo, cloning from repoURL if missing.
func EnsureGitRepo(wikiDir, repoURL string) error {
	cmd := exec.Command("git", "rev-parse", "--is-inside-work-tree")
	cmd.Dir = wikiDir
	if err := cmd.Run(); err == nil {
		return nil
	}

	if repoURL == "" {
		return fmt.Errorf("directory %s is not a git repository and no REPO_URL provided", wikiDir)
	}

	_ = os.MkdirAll(wikiDir, 0755)
	cloneCmd := exec.Command("git", "clone", repoURL, wikiDir)
	out, err := cloneCmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("failed to clone %s: %s (%w)", repoURL, string(out), err)
	}

	return nil
}

// GetCurrentCommit returns the HEAD commit hash or "unknown".
func GetCurrentCommit(wikiDir string) string {
	cmd := exec.Command("git", "rev-parse", "HEAD")
	cmd.Dir = wikiDir
	out, err := cmd.Output()
	if err != nil {
		return "unknown"
	}
	return strings.TrimSpace(string(out))
}

// PullRepo executes git pull --ff-only and updates sync metadata safely.
func (s *Syncer) PullRepo(trigger string) (bool, string, string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now().UTC().Format(time.RFC3339)
	s.metadata.LastSyncAt = now
	s.metadata.LastSyncTrigger = trigger

	cmd := exec.Command("git", "pull", "--ff-only")
	cmd.Dir = s.wikiDir

	var outBuf bytes.Buffer
	cmd.Stdout = &outBuf
	cmd.Stderr = &outBuf

	err := cmd.Run()
	output := strings.TrimSpace(outBuf.String())
	commit := GetCurrentCommit(s.wikiDir)
	s.metadata.LastSyncCommit = commit

	if err != nil {
		s.metadata.LastSyncStatus = "failed"
		s.metadata.LastSyncError = output
		return false, commit, output
	}

	s.metadata.LastSyncStatus = "success"
	s.metadata.LastSyncError = ""
	return true, commit, output
}

// GetMetadata returns a snapshot of sync metadata.
func (s *Syncer) GetMetadata() SyncMetadata {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.metadata
}
