package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"go.mau.fi/whatsmeow/types"
)

func TestBuildWatchUpEventContractAndSignature(t *testing.T) {
	timestamp := time.Date(2026, 10, 4, 10, 0, 0, 0, time.FixedZone("IDT", 3*60*60))
	payload := WebhookPayload{MessageID: "synthetic-event-1", Sender: "synthetic-sender", DisplayName: "שם פרופיל בלבד", IsRecognized: false, ChatJID: "synthetic-chat", Content: "בדיקה"}
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
	if event["account"].(map[string]any)["is_recognized"] != false {
		t.Fatalf("push name must not mark an unsaved sender as recognized: %#v", event["account"])
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

func TestBuildWatchUpGroupEventContainsLiveMetadataWithoutImageURL(t *testing.T) {
	group := &types.GroupInfo{
		JID: types.NewJID("12345", types.GroupServer), GroupName: types.GroupName{Name: "קבוצת בדיקה"}, ParticipantCount: 7,
		Participants: []types.GroupParticipant{{
			JID: types.NewJID("261391827087520", types.HiddenUserServer), PhoneNumber: types.NewJID("972501234567", types.DefaultUserServer), DisplayName: "זר בקבוצה",
		}},
	}
	contacts := map[types.JID]types.ContactInfo{
		types.NewJID("972501234567", types.DefaultUserServer): {Found: true, FullName: "איש קשר שמור"},
	}
	body, err := buildWatchUpGroupEvent(group, contacts, "picture-1", "image/jpeg", "c3ludGhldGlj", time.Unix(10, 0), "tenant", "child", "secret")
	if err != nil {
		t.Fatal(err)
	}
	var event map[string]any
	if err := json.Unmarshal(body, &event); err != nil {
		t.Fatal(err)
	}
	if event["type"] != "group.snapshot" || event["event_id"] == "" {
		t.Fatalf("unexpected group event: %#v", event)
	}
	payload := event["payload"].(map[string]any)
	if payload["name"] != "קבוצת בדיקה" || payload["participantCount"] != float64(7) || payload["imageBase64"] != "c3ludGhldGlj" {
		t.Fatalf("unexpected group payload: %#v", payload)
	}
	people, _ := payload["participants"].([]any)
	if len(people) != 1 {
		t.Fatalf("participants = %#v", payload["participants"])
	}
	person := people[0].(map[string]any)
	if person["phone"] != "972501234567" || person["name"] != "איש קשר שמור" || person["isRecognized"] != true {
		t.Fatalf("participant = %#v", person)
	}
	if bytes := string(body); strings.Contains(bytes, "https://") || strings.Contains(bytes, "picture-1") || strings.Contains(bytes, "261391827087520") {
		t.Fatalf("group event leaked source image data or a raw LID: %s", bytes)
	}
}

func TestWatchUpGroupPeopleRecognizesOnlySavedContacts(t *testing.T) {
	jid := types.NewJID("972501234567", types.DefaultUserServer)
	group := &types.GroupInfo{Participants: []types.GroupParticipant{{JID: jid, PhoneNumber: jid, DisplayName: "שם פרופיל"}}}
	people := watchUpGroupPeople(group, map[types.JID]types.ContactInfo{jid: {Found: true}})
	if len(people) != 1 || !people[0].IsRecognized {
		t.Fatalf("saved contact must be recognized even without a stored name: %#v", people)
	}
	people = watchUpGroupPeople(group, map[types.JID]types.ContactInfo{})
	if len(people) != 1 || people[0].IsRecognized {
		t.Fatalf("profile name alone must never be recognized: %#v", people)
	}
}

func TestBuildWatchUpStatusEventAlwaysIncludesPayloadObject(t *testing.T) {
	body, err := buildWatchUpStatusEvent("connected", time.Unix(10, 0), "tenant", "child", "secret")
	if err != nil {
		t.Fatal(err)
	}
	var event map[string]any
	if err := json.Unmarshal(body, &event); err != nil {
		t.Fatal(err)
	}
	if payload, ok := event["payload"].(map[string]any); !ok || len(payload) != 0 {
		t.Fatalf("status payload must be an empty object: %#v", event["payload"])
	}
}

func TestDownloadWatchUpGroupImageRejectsNonHTTPS(t *testing.T) {
	if _, _, err := downloadWatchUpGroupImage(context.Background(), "http://example.test/image.jpg"); err == nil {
		t.Fatal("expected non-HTTPS group image URL to be rejected")
	}
}

func TestDownloadWatchUpGroupImageCapsAndValidatesContent(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write(append([]byte{0xff, 0xd8, 0xff, 0xe0}, []byte("synthetic jpeg")...))
	}))
	defer server.Close()
	previous := watchUpImageHTTPClient
	watchUpImageHTTPClient = server.Client()
	defer func() { watchUpImageHTTPClient = previous }()
	mimeType, encoded, err := downloadWatchUpGroupImage(context.Background(), server.URL)
	if err != nil || mimeType != "image/jpeg" || encoded == "" {
		t.Fatalf("mime=%q encoded=%q err=%v", mimeType, encoded, err)
	}
}

func TestWatchUpSecretReadsOnlyConfiguredSecretFile(t *testing.T) {
	path := t.TempDir() + "/watchup-secret"
	if err := os.WriteFile(path, []byte(" synthetic-secret\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("WATCHUP_WEBHOOK_SECRET_FILE", path)
	t.Setenv("WATCHUP_WEBHOOK_SECRET", "must-not-be-used")
	secret, err := watchUpSecret()
	if err != nil || secret != "synthetic-secret" {
		t.Fatalf("secret=%q err=%v", secret, err)
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

func TestWatchUpURLAllowedOnlyForInternalOrLoopbackEndpoint(t *testing.T) {
	if !watchUpURLAllowed(watchUpWebhookURL) {
		t.Fatal("fixed internal endpoint must be allowed")
	}
	if !watchUpURLAllowed("http://127.0.0.1:8769/watchup/events") {
		t.Fatal("loopback test endpoint must be allowed")
	}
	for _, url := range []string{
		"http://127.0.0.1:8769/whatsapp/webhook",
		"http://127.0.0.1:8769/watchup/events/",
		"https://example.test/watchup/events",
	} {
		if watchUpURLAllowed(url) {
			t.Fatalf("unexpected allowed URL: %s", url)
		}
	}
}
