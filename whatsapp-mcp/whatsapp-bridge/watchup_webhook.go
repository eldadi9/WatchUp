package main

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/types"
)

const (
	watchUpWebhookURL       = "http://watchup-api:8769/watchup/events"
	watchUpWebhookPath      = "/watchup/events"
	watchUpDeliveryTimeout  = 4 * time.Second
	watchUpDeliveryAttempts = 2
	watchUpGroupImageLimit  = 96 * 1024
)

var watchUpHTTPClient = &http.Client{Timeout: watchUpDeliveryTimeout}
var watchUpImageHTTPClient = &http.Client{
	Timeout: watchUpDeliveryTimeout,
	CheckRedirect: func(req *http.Request, via []*http.Request) error {
		if len(via) >= 3 || req.URL.Scheme != "https" || req.URL.User != nil {
			return errors.New("unsafe group image redirect")
		}
		return nil
	},
}

type watchUpEvent struct {
	EventID         string         `json:"event_id"`
	Type            string         `json:"type"`
	Source          string         `json:"source"`
	SourceTimestamp time.Time      `json:"source_timestamp"`
	TenantID        string         `json:"tenant_id"`
	ChildID         string         `json:"child_id"`
	Account         map[string]any `json:"account"`
	Payload         any            `json:"payload,omitempty"`
}

type watchUpPerson struct {
	Name         string `json:"name,omitempty"`
	Phone        string `json:"phone,omitempty"`
	IsRecognized bool   `json:"isRecognized"`
}

type watchUpGroupPayload struct {
	Name             string          `json:"name"`
	ParticipantCount int             `json:"participantCount"`
	Participants     []watchUpPerson `json:"participants"`
	ImageMimeType    string          `json:"imageMimeType,omitempty"`
	ImageBase64      string          `json:"imageBase64,omitempty"`
}

func watchUpGroupPeople(group *types.GroupInfo, contacts map[types.JID]types.ContactInfo) []watchUpPerson {
	people := make([]watchUpPerson, 0)
	if group == nil {
		return people
	}
	for _, person := range group.Participants {
		if len(people) >= 80 {
			break
		}
		phone := person.PhoneNumber.User
		if phone == "" && person.JID.Server == types.DefaultUserServer {
			phone = person.JID.User
		}
		contact := contacts[person.PhoneNumber.ToNonAD()]
		if !contact.Found {
			contact = contacts[person.JID.ToNonAD()]
		}
		name := strings.TrimSpace(contact.FullName)
		if name == "" {
			name = strings.TrimSpace(contact.FirstName)
		}
		recognized := contact.Found
		if name == "" {
			name = strings.TrimSpace(person.DisplayName)
		}
		if phone == "" && name == "" {
			continue
		}
		people = append(people, watchUpPerson{Name: name, Phone: phone, IsRecognized: recognized})
	}
	return people
}

func watchUpURLAllowed(rawURL string) bool {
	parsed, err := url.Parse(rawURL)
	if err != nil || parsed.Scheme != "http" || parsed.Path != watchUpWebhookPath || parsed.RawQuery != "" || parsed.Fragment != "" || parsed.User != nil {
		return false
	}
	host := strings.ToLower(parsed.Hostname())
	if parsed.Port() != "8769" {
		return false
	}
	return host == "watchup-api" || host == "127.0.0.1" || host == "localhost" || net.ParseIP(host).IsLoopback()
}

func watchUpURL() (string, error) {
	rawURL := strings.TrimSpace(os.Getenv("WATCHUP_WEBHOOK_URL"))
	if rawURL == "" {
		rawURL = watchUpWebhookURL
	}
	if !watchUpURLAllowed(rawURL) {
		return "", errors.New("WATCHUP_WEBHOOK_URL must be the WatchUp internal endpoint or a loopback test endpoint")
	}
	return rawURL, nil
}

func watchUpSecret() (string, error) {
	path := strings.TrimSpace(os.Getenv("WATCHUP_WEBHOOK_SECRET_FILE"))
	if path != "" {
		contents, err := os.ReadFile(path)
		if err != nil {
			return "", fmt.Errorf("read WATCHUP_WEBHOOK_SECRET_FILE: %w", err)
		}
		if secret := strings.TrimSpace(string(contents)); secret != "" {
			return secret, nil
		}
		return "", errors.New("WATCHUP_WEBHOOK_SECRET_FILE is empty")
	}
	return "", errors.New("WATCHUP_WEBHOOK_SECRET_FILE is required")
}

// watchUpEnabled keeps the legacy generic webhook path independent. WatchUp
// delivery is enabled only by its dedicated secret configuration; it never
// falls back to WEBHOOK_URL or an unsigned request.
func watchUpEnabled() bool {
	return strings.TrimSpace(os.Getenv("WATCHUP_WEBHOOK_SECRET_FILE")) != ""
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
	return json.Marshal(watchUpEvent{EventID: payload.MessageID, Type: eventType, Source: "whatsapp-bridge", SourceTimestamp: sourceTimestamp.UTC(), TenantID: tenantID, ChildID: childID, Account: map[string]any{"chat_jid": payload.ChatJID, "chat_type": payload.ChatType, "sender": payload.Sender, "display_name": payload.DisplayName, "is_recognized": payload.IsRecognized, "is_from_me": payload.IsFromMe}, Payload: payload})
}

func buildWatchUpStatusEvent(status string, sourceTimestamp time.Time, tenantID, childID, secret string) ([]byte, error) {
	if secret == "" || tenantID == "" || childID == "" || status == "" {
		return nil, errors.New("status event requires secret, tenant_id, child_id, and status")
	}
	return json.Marshal(watchUpEvent{EventID: fmt.Sprintf("connection:%s:%d", status, sourceTimestamp.UTC().UnixNano()), Type: "connection.status", Source: "whatsapp-bridge", SourceTimestamp: sourceTimestamp.UTC(), TenantID: tenantID, ChildID: childID, Account: map[string]any{"status": status}, Payload: map[string]any{}})
}

func buildWatchUpGroupEvent(group *types.GroupInfo, contacts map[types.JID]types.ContactInfo, pictureID, imageMimeType, imageBase64 string, sourceTimestamp time.Time, tenantID, childID, secret string) ([]byte, error) {
	if secret == "" || tenantID == "" || childID == "" || group == nil || group.JID.IsEmpty() || strings.TrimSpace(group.Name) == "" {
		return nil, errors.New("group event requires secret, tenant_id, child_id, jid, and name")
	}
	participantCount := group.ParticipantCount
	if participantCount == 0 {
		participantCount = len(group.Participants)
	}
	people := watchUpGroupPeople(group, contacts)
	phones := make([]string, 0, len(people))
	for _, person := range people {
		phones = append(phones, person.Phone)
	}
	version := fmt.Sprintf("%s|%s|%d|%s|%s", group.JID.String(), group.Name, participantCount, pictureID, strings.Join(phones, ","))
	digest := sha256.Sum256([]byte(version))
	return json.Marshal(watchUpEvent{
		EventID: fmt.Sprintf("group:%x", digest[:16]), Type: "group.snapshot", Source: "whatsapp-bridge",
		SourceTimestamp: sourceTimestamp.UTC(), TenantID: tenantID, ChildID: childID,
		Account: map[string]any{"chat_jid": group.JID.String(), "chat_type": "group", "display_name": group.Name},
		Payload: watchUpGroupPayload{Name: group.Name, ParticipantCount: participantCount, Participants: people, ImageMimeType: imageMimeType, ImageBase64: imageBase64},
	})
}

func downloadWatchUpGroupImage(ctx context.Context, rawURL string) (string, string, error) {
	parsed, err := url.Parse(rawURL)
	if err != nil || parsed.Scheme != "https" || parsed.Hostname() == "" || parsed.User != nil {
		return "", "", errors.New("unsafe group image URL")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return "", "", errors.New("create group image request")
	}
	resp, err := watchUpImageHTTPClient.Do(req)
	if err != nil {
		return "", "", errors.New("download group image")
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", "", errors.New("group image request rejected")
	}
	data, err := io.ReadAll(io.LimitReader(resp.Body, watchUpGroupImageLimit+1))
	if err != nil || len(data) == 0 || len(data) > watchUpGroupImageLimit {
		return "", "", errors.New("invalid group image size")
	}
	mimeType := http.DetectContentType(data)
	if mimeType != "image/jpeg" && mimeType != "image/png" && mimeType != "image/webp" {
		return "", "", errors.New("unsupported group image type")
	}
	return mimeType, base64.StdEncoding.EncodeToString(data), nil
}

func syncWatchUpGroups(client *whatsmeow.Client) (int, error) {
	if client == nil {
		return 0, errors.New("WhatsApp client is required")
	}
	secret, err := watchUpSecret()
	if err != nil {
		return 0, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	groups, err := client.GetJoinedGroups(ctx)
	if err != nil {
		return 0, errors.New("load joined groups")
	}
	contacts, err := client.Store.Contacts.GetAllContacts(ctx)
	if err != nil {
		contacts = map[types.JID]types.ContactInfo{}
	}
	tenantID := strings.TrimSpace(os.Getenv("WATCHUP_TENANT_ID"))
	childID := strings.TrimSpace(os.Getenv("WATCHUP_CHILD_ID"))
	delivered := 0
	var deliveryErrors []error
	for index, group := range groups {
		pictureID, imageMimeType, imageBase64 := "", "", ""
		if picture, pictureErr := client.GetProfilePictureInfo(ctx, group.JID, &whatsmeow.GetProfilePictureParams{Preview: true}); pictureErr == nil && picture != nil {
			pictureID = picture.ID
			imageMimeType, imageBase64, _ = downloadWatchUpGroupImage(ctx, picture.URL)
		}
		body, buildErr := buildWatchUpGroupEvent(group, contacts, pictureID, imageMimeType, imageBase64, time.Now(), tenantID, childID, secret)
		if buildErr != nil {
			deliveryErrors = append(deliveryErrors, fmt.Errorf("group %d contract: %w", index, buildErr))
			continue
		}
		if sendErr := sendWatchUpEvent(ctx, body, secret); sendErr != nil {
			deliveryErrors = append(deliveryErrors, fmt.Errorf("group %d delivery: %w", index, sendErr))
			continue
		}
		delivered++
	}
	return delivered, errors.Join(deliveryErrors...)
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

func sendWatchUpEvent(ctx context.Context, body []byte, secret string) error {
	endpoint, err := watchUpURL()
	if err != nil {
		return err
	}
	signature, err := watchUpSignature(secret, body)
	if err != nil {
		return err
	}
	var lastErr error
	for attempt := 0; attempt < watchUpDeliveryAttempts; attempt++ {
		req, reqErr := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
		if reqErr != nil {
			return reqErr
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-WatchUp-Signature", signature)
		resp, doErr := watchUpHTTPClient.Do(req)
		if doErr == nil && resp != nil {
			_ = resp.Body.Close()
			if resp.StatusCode >= 200 && resp.StatusCode < 300 {
				return nil
			}
			if resp.StatusCode >= 400 && resp.StatusCode < 500 {
				return fmt.Errorf("WatchUp rejected event with status %d", resp.StatusCode)
			}
			lastErr = fmt.Errorf("WatchUp returned status %d", resp.StatusCode)
		} else {
			lastErr = doErr
		}
		if attempt+1 < watchUpDeliveryAttempts {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(150 * time.Millisecond):
			}
		}
	}
	if lastErr == nil {
		lastErr = errors.New("WatchUp delivery failed")
	}
	return lastErr
}

func sendWatchUpMessageEvent(payload WebhookPayload, timestamp time.Time) error {
	secret, err := watchUpSecret()
	if err != nil {
		return err
	}
	body, err := buildWatchUpEvent(payload, timestamp, strings.TrimSpace(os.Getenv("WATCHUP_TENANT_ID")), strings.TrimSpace(os.Getenv("WATCHUP_CHILD_ID")), secret)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), watchUpDeliveryTimeout*time.Duration(watchUpDeliveryAttempts))
	defer cancel()
	return sendWatchUpEvent(ctx, body, secret)
}

func sendWatchUpConnectionStatus(status string, timestamp time.Time) error {
	secret, err := watchUpSecret()
	if err != nil {
		return err
	}
	body, err := buildWatchUpStatusEvent(status, timestamp, strings.TrimSpace(os.Getenv("WATCHUP_TENANT_ID")), strings.TrimSpace(os.Getenv("WATCHUP_CHILD_ID")), secret)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), watchUpDeliveryTimeout*time.Duration(watchUpDeliveryAttempts))
	defer cancel()
	return sendWatchUpEvent(ctx, body, secret)
}
