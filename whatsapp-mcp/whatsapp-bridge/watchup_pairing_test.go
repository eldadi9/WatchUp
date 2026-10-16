package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"go.mau.fi/whatsmeow"
)

type fakePairingAPI struct {
	mu        sync.Mutex
	requested bool
	reports   []string
}

func (f *fakePairingAPI) report(state, code string) (bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.reports = append(f.reports, state)
	if state == "timeout" || state == "paired" {
		f.requested = false
	}
	return f.requested, nil
}

func (f *fakePairingAPI) set(requested bool) {
	f.mu.Lock()
	f.requested = requested
	f.mu.Unlock()
}

func (f *fakePairingAPI) states() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]string(nil), f.reports...)
}

func fakeQR(items ...whatsmeow.QRChannelItem) (watchUpQRSource, *int) {
	calls := 0
	return func(ctx context.Context) (<-chan whatsmeow.QRChannelItem, error) {
		calls++
		out := make(chan whatsmeow.QRChannelItem)
		go func() {
			defer close(out)
			for _, item := range items {
				select {
				case out <- item:
				case <-ctx.Done():
					return
				}
			}
			<-ctx.Done()
		}()
		return out, nil
	}, &calls
}

func code(value string) whatsmeow.QRChannelItem {
	return whatsmeow.QRChannelItem{Event: whatsmeow.QRChannelEventCode, Code: value}
}

func TestOnDemandPairingNeverStartsQRWithoutRequest(t *testing.T) {
	api := &fakePairingAPI{}
	source, calls := fakeQR(code("never"))
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Millisecond)
	defer cancel()
	if runOnDemandPairing(ctx, api.report, source, 5*time.Millisecond) {
		t.Fatal("paired without a request")
	}
	if *calls != 0 {
		t.Fatalf("QR started %d times without a parent request", *calls)
	}
	for _, state := range api.states() {
		if state != "unpaired" {
			t.Fatalf("unexpected report %q", state)
		}
	}
}

func TestOnDemandPairingReportsCodesAndSuccess(t *testing.T) {
	api := &fakePairingAPI{requested: true}
	source, calls := fakeQR(code("c1"), code("c2"), whatsmeow.QRChannelSuccess)
	if !runOnDemandPairing(context.Background(), api.report, source, time.Millisecond) {
		t.Fatal("expected pairing success")
	}
	got := api.states()
	want := []string{"unpaired", "qr", "qr", "paired"}
	if len(got) != len(want) {
		t.Fatalf("reports = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("reports = %v, want %v", got, want)
		}
	}
	if *calls != 1 {
		t.Fatalf("QR started %d times", *calls)
	}
}

func TestOnDemandPairingStopsWhenParentCancels(t *testing.T) {
	api := &fakePairingAPI{requested: true}
	source, calls := fakeQR(code("c1"), code("c2"))
	cancelOnFirstCode := func(state, value string) (bool, error) {
		if state == "qr" {
			api.set(false)
		}
		return api.report(state, value)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 80*time.Millisecond)
	defer cancel()
	if runOnDemandPairing(ctx, cancelOnFirstCode, source, 5*time.Millisecond) {
		t.Fatal("paired after cancel")
	}
	if *calls != 1 {
		t.Fatalf("QR restarted after cancel: %d", *calls)
	}
	for _, state := range api.states() {
		if state == "timeout" {
			t.Fatal("a parent cancel must not be reported as timeout")
		}
	}
}

func TestOnDemandPairingTimeoutReturnsToIdleWithoutRetry(t *testing.T) {
	api := &fakePairingAPI{requested: true}
	source, calls := fakeQR(code("c1"), whatsmeow.QRChannelTimeout)
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Millisecond)
	defer cancel()
	if runOnDemandPairing(ctx, api.report, source, 5*time.Millisecond) {
		t.Fatal("paired after timeout")
	}
	if *calls != 1 {
		t.Fatalf("QR retried %d times without a new request", *calls)
	}
}

func TestPostWatchUpPairingSignsAndBindsToOwnChild(t *testing.T) {
	secret := "bridge-secret-rotem-000000000000000"
	var seen watchUpPairingReport
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		if r.URL.Path != watchUpPairingPath || !validWatchUpSignature(secret, body, r.Header.Get("X-WatchUp-Signature")) {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		_ = json.Unmarshal(body, &seen)
		_, _ = w.Write([]byte(`{"pairing_requested":true}`))
	}))
	defer server.Close()
	requested, err := postWatchUpPairing(context.Background(), server.URL+watchUpPairingPath, secret, "family-b", "rotem", "qr", "2@code")
	if err != nil || !requested {
		t.Fatalf("requested=%v err=%v", requested, err)
	}
	if seen.TenantID != "family-b" || seen.ChildID != "rotem" || seen.State != "qr" || seen.Code != "2@code" || time.Since(seen.SentAt) > time.Minute {
		t.Fatalf("unexpected report %+v", seen)
	}
	if _, err := postWatchUpPairing(context.Background(), server.URL+watchUpPairingPath, "wrong-secret-0000000000", "family-b", "rotem", "unpaired", ""); err == nil {
		t.Fatal("expected rejected report with a wrong secret")
	}
}

func TestWatchUpPairingURLFollowsTheInternalEventsEndpoint(t *testing.T) {
	t.Setenv("WATCHUP_WEBHOOK_URL", "http://watchup-api:8769/watchup/events")
	got, err := watchUpPairingURL()
	if err != nil || got != "http://watchup-api:8769/watchup/bridge/pairing" {
		t.Fatalf("got %q err %v", got, err)
	}
	t.Setenv("WATCHUP_WEBHOOK_URL", "http://evil.example:8769/watchup/events")
	if _, err := watchUpPairingURL(); err == nil {
		t.Fatal("external pairing endpoint must be refused")
	}
}

func TestOnDemandPairingIsOptIn(t *testing.T) {
	t.Setenv("WATCHUP_PAIRING_MODE", "")
	if watchUpOnDemandPairing() {
		t.Fatal("legacy bridges must keep startup pairing")
	}
	t.Setenv("WATCHUP_PAIRING_MODE", "on-demand")
	if !watchUpOnDemandPairing() {
		t.Fatal("on-demand mode not detected")
	}
}
