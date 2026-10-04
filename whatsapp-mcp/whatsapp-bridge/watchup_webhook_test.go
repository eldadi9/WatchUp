package main

import (
	"encoding/json"
	"testing"
	"time"
)

func TestBuildWatchUpEventContractAndSignature(t *testing.T) {
	timestamp := time.Date(2026, 10, 4, 10, 0, 0, 0, time.FixedZone("IDT", 3*60*60))
	payload := WebhookPayload{MessageID: "synthetic-event-1", Sender: "synthetic-sender", ChatJID: "synthetic-chat", Content: "בדיקה"}
	body, err := buildWatchUpEvent(payload, timestamp, "tenant-test", "child-test", "synthetic-secret")
	if err != nil {
		t.Fatal(err)
	}
	var event map[string]any
	if err := json.Unmarshal(body, &event); err != nil {
		t.Fatal(err)
	}
	if event["event_id"] != "synthetic-event-1" || event["type"] != "message.received" || event["source"] != "whatsapp-bridge" {
		t.Fatalf("unexpected contract identifiers: %#v", event)
	}
	if event["tenant_id"] != "tenant-test" || event["child_id"] != "child-test" {
		t.Fatalf("tenant/child missing: %#v", event)
	}
	if event["source_timestamp"] != "2026-10-04T07:00:00Z" {
		t.Fatalf("timestamp = %q", event["source_timestamp"])
	}
	signature, err := watchUpSignature("synthetic-secret", body)
	if err != nil || !validWatchUpSignature("synthetic-secret", body, signature) {
		t.Fatal("expected valid HMAC signature")
	}
	if validWatchUpSignature("synthetic-secret", append(body, 'x'), signature) {
		t.Fatal("signature must cover the exact JSON bytes")
	}
}

func TestWatchUpHelpersRefuseMissingSecret(t *testing.T) {
	payload := WebhookPayload{MessageID: "synthetic-event-1"}
	if _, err := buildWatchUpEvent(payload, time.Now(), "tenant", "child", ""); err == nil {
		t.Fatal("expected missing secret refusal")
	}
	if _, err := watchUpSignature("", []byte("{}")); err == nil {
		t.Fatal("expected missing secret refusal")
	}
}

func TestWatchUpURLAllowedOnlyForFixedLoopbackEndpoint(t *testing.T) {
	if !watchUpURLAllowed(watchUpWebhookURL) {
		t.Fatal("fixed loopback endpoint must be allowed")
	}
	for _, url := range []string{
		"http://localhost:8769/watchup/events",
		"http://127.0.0.1:8769/whatsapp/webhook",
		"http://127.0.0.1:8769/watchup/events/",
		"https://example.test/watchup/events",
	} {
		if watchUpURLAllowed(url) {
			t.Fatalf("unexpected allowed URL: %s", url)
		}
	}
}
