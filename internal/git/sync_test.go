package git

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"testing"
)

func TestVerifyGitHubSignature(t *testing.T) {
	secret := "test-secret-123"
	payload := []byte(`{"ref":"refs/heads/main"}`)

	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(payload)
	validHex := hex.EncodeToString(mac.Sum(nil))

	if !VerifyGitHubSignature(payload, "sha256="+validHex, secret) {
		t.Error("expected valid signature to pass")
	}

	if VerifyGitHubSignature(payload, "sha256=invalidhex", secret) {
		t.Error("expected invalid signature to fail")
	}

	if VerifyGitHubSignature(payload, "sha256="+validHex, "wrong-secret") {
		t.Error("expected wrong secret to fail")
	}
}

func TestVerifyGitLabToken(t *testing.T) {
	secret := "secret-token"
	if !VerifyGitLabToken("secret-token", secret) {
		t.Error("expected token match")
	}
	if VerifyGitLabToken("wrong-token", secret) {
		t.Error("expected token mismatch")
	}
}
