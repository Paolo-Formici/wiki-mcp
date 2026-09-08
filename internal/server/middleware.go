package server

import (
	"crypto/subtle"
	"encoding/json"
	"net/http"
	"strings"
)

// TokenAuthMiddleware validates Bearer token if authToken is non-empty.
// Endpoints /health and /webhook bypass this check.
func TokenAuthMiddleware(authToken string, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if authToken == "" || r.URL.Path == "/health" || r.URL.Path == "/webhook" {
			next.ServeHTTP(w, r)
			return
		}

		authHeader := r.Header.Get("Authorization")
		if !strings.HasPrefix(authHeader, "Bearer ") {
			writeJSONError(w, http.StatusUnauthorized, "Unauthorized: Missing or malformed Bearer token")
			return
		}

		token := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))
		if subtle.ConstantTimeCompare([]byte(token), []byte(authToken)) != 1 {
			writeJSONError(w, http.StatusUnauthorized, "Unauthorized: Invalid token")
			return
		}

		next.ServeHTTP(w, r)
	})
}

func writeJSONError(w http.ResponseWriter, statusCode int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": message})
}
