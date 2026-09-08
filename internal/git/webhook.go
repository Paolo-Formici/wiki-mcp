package git

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"strings"
)

// VerifyGitHubSignature verifies the X-Hub-Signature-256 header against the payload and secret.
func VerifyGitHubSignature(payload []byte, signatureHeader, secret string) bool {
	if signatureHeader == "" || secret == "" {
		return false
	}

	sig := strings.TrimPrefix(signatureHeader, "sha256=")
	expectedMAC, err := hex.DecodeString(sig)
	if err != nil {
		return false
	}

	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(payload)
	computedMAC := mac.Sum(nil)

	return hmac.Equal(expectedMAC, computedMAC)
}

// VerifyGitLabToken verifies the X-Gitlab-Token header against secret.
func VerifyGitLabToken(tokenHeader, secret string) bool {
	if tokenHeader == "" || secret == "" {
		return false
	}
	return hmac.Equal([]byte(tokenHeader), []byte(secret))
}
