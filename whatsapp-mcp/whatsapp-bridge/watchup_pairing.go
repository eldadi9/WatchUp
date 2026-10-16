package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"go.mau.fi/whatsmeow"
)

const (
	watchUpPairingPath    = "/watchup/bridge/pairing"
	watchUpPairingIdle    = 10 * time.Second
	watchUpPairingTimeout = 4 * time.Minute
)

// watchUpOnDemandPairing keeps an unpaired bridge silent until a parent of
// its own child asks for a code. Unset keeps the legacy startup QR.
func watchUpOnDemandPairing() bool {
	return strings.TrimSpace(os.Getenv("WATCHUP_PAIRING_MODE")) == "on-demand"
}

func watchUpPairingURL() (string, error) {
	events, err := watchUpURL()
	if err != nil {
		return "", err
	}
	parsed, _ := url.Parse(events)
	parsed.Path = watchUpPairingPath
	return parsed.String(), nil
}

type watchUpPairingReport struct {
	TenantID string    `json:"tenant_id"`
	ChildID  string    `json:"child_id"`
	State    string    `json:"state"`
	Code     string    `json:"code,omitempty"`
	SentAt   time.Time `json:"sent_at"`
}

// postWatchUpPairing reports this bridge's state and returns whether a parent
// asked to pair this bridge's child. The API binds the answer to the secret.
func postWatchUpPairing(ctx context.Context, endpoint, secret, tenantID, childID, state, code string) (bool, error) {
	if secret == "" || tenantID == "" || childID == "" {
		return false, errors.New("pairing report requires secret, tenant_id, and child_id")
	}
	body, err := json.Marshal(watchUpPairingReport{TenantID: tenantID, ChildID: childID, State: state, Code: code, SentAt: time.Now().UTC()})
	if err != nil {
		return false, err
	}
	signature, err := watchUpSignature(secret, body)
	if err != nil {
		return false, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return false, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-WatchUp-Signature", signature)
	resp, err := watchUpHTTPClient.Do(req)
	if err != nil {
		return false, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return false, fmt.Errorf("WatchUp pairing report rejected with status %d", resp.StatusCode)
	}
	var answer struct {
		PairingRequested bool `json:"pairing_requested"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&answer); err != nil {
		return false, err
	}
	return answer.PairingRequested, nil
}

func reportWatchUpPairing(state, code string) (bool, error) {
	secret, err := watchUpSecret()
	if err != nil {
		return false, err
	}
	endpoint, err := watchUpPairingURL()
	if err != nil {
		return false, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), watchUpDeliveryTimeout)
	defer cancel()
	return postWatchUpPairing(ctx, endpoint, secret, strings.TrimSpace(os.Getenv("WATCHUP_TENANT_ID")), strings.TrimSpace(os.Getenv("WATCHUP_CHILD_ID")), state, code)
}

type watchUpQRSource func(ctx context.Context) (<-chan whatsmeow.QRChannelItem, error)

// runOnDemandPairing returns true once paired. It never asks WhatsApp for a
// code unless the API reports a pending parent request, and a timeout or
// cancel returns to idle instead of retrying (repeated codes get blocked).
func runOnDemandPairing(ctx context.Context, report func(state, code string) (bool, error), startQR watchUpQRSource, idle time.Duration) bool {
	for {
		if requested, err := report("unpaired", ""); err == nil && requested {
			if runOneWatchUpPairing(ctx, report, startQR) {
				return true
			}
		}
		select {
		case <-ctx.Done():
			return false
		case <-time.After(idle):
		}
	}
}

func runOneWatchUpPairing(ctx context.Context, report func(state, code string) (bool, error), startQR watchUpQRSource) bool {
	qrCtx, cancel := context.WithTimeout(ctx, watchUpPairingTimeout)
	defer cancel()
	codes, err := startQR(qrCtx)
	if err != nil {
		_, _ = report("timeout", "")
		return false
	}
	cancelled := false
	for evt := range codes {
		switch evt.Event {
		case whatsmeow.QRChannelEventCode:
			if stillRequested, reportErr := report("qr", evt.Code); reportErr == nil && !stillRequested {
				cancelled = true
				cancel()
			}
		case whatsmeow.QRChannelSuccess.Event:
			_, _ = report("paired", "")
			return true
		default:
			_, _ = report("timeout", "")
			return false
		}
	}
	if !cancelled {
		_, _ = report("timeout", "")
	}
	return false
}
