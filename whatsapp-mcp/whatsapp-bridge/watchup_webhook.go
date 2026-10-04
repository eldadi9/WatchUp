package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"time"
)

const watchUpWebhookURL = "http://127.0.0.1:8769/watchup/events"

type watchUpEvent struct {
	EventID         string         `json:"event_id"`
	Type            string         `json:"type"`
	Source          string         `json:"source"`
	SourceTimestamp time.Time      `json:"source_timestamp"`
	TenantID        string         `json:"tenant_id"`
	ChildID         string         `json:"child_id"`
	Account         map[string]any `json:"account"`
	Payload         WebhookPayload `json:"payload"`
}

func watchUpURLAllowed(url string) bool {
	return url == watchUpWebhookURL
}

func buildWatchUpEvent(payload WebhookPayload, sourceTimestamp time.Time, tenantID, childID, secret string) ([]byte, error) {
	if secret == "" {
		return nil, errors.New("WATCHUP_WEBHOOK_SECRET is required")
	}
	if tenantID == "" || childID == "" || payload.MessageID == "" {
		return nil, errors.New("event_id, tenant_id, and child_id are required")
	}
	eventType := "message.received"
	if payload.EventType == "reaction" {
		eventType = "reaction.received"
	}
	return json.Marshal(watchUpEvent{
		EventID:         payload.MessageID,
		Type:            eventType,
		Source:          "whatsapp-bridge",
		SourceTimestamp: sourceTimestamp.UTC(),
		TenantID:        tenantID,
		ChildID:         childID,
		Account: map[string]any{
			"chat_jid":   payload.ChatJID,
			"sender":     payload.Sender,
			"is_from_me": payload.IsFromMe,
		},
		Payload: payload,
	})
}

func watchUpSignature(secret string, body []byte) (string, error) {
	if secret == "" {
		return "", errors.New("WATCHUP_WEBHOOK_SECRET is required")
	}
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write(body)
	return fmt.Sprintf("sha256=%x", mac.Sum(nil)), nil
}

func validWatchUpSignature(secret string, body []byte, signature string) bool {
	expected, err := watchUpSignature(secret, body)
	return err == nil && hmac.Equal([]byte(signature), []byte(expected))
}
