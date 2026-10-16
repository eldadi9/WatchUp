package main

import (
	"context"
	"testing"

	"go.mau.fi/whatsmeow/store"
	"go.mau.fi/whatsmeow/types"
)

type mockWatchUpContacts struct {
	byJID map[string]types.ContactInfo
}

func (m mockWatchUpContacts) GetContact(_ context.Context, jid types.JID) (types.ContactInfo, error) {
	if info, ok := m.byJID[jid.ToNonAD().String()]; ok {
		return info, nil
	}
	return types.ContactInfo{}, nil
}

func TestWatchUpSavedContactRequiresAddressBookName(t *testing.T) {
	phone := types.NewJID("972501111111", types.DefaultUserServer)
	contacts := mockWatchUpContacts{byJID: map[string]types.ContactInfo{
		phone.String(): {Found: true, PushName: "שם פרופיל בלבד"},
	}}
	if name, recognized := watchUpSavedContactFromStore(contacts, nil, phone); recognized || name != "" {
		t.Fatalf("push name must not recognize a sender: name=%q recognized=%v", name, recognized)
	}
	contacts.byJID[phone.String()] = types.ContactInfo{Found: true, FullName: "איש קשר שמור"}
	name, recognized := watchUpSavedContactFromStore(contacts, nil, phone)
	if !recognized || name != "איש קשר שמור" {
		t.Fatalf("saved contact = %q %v", name, recognized)
	}
}

func TestWatchUpSavedContactResolvesLIDToPhone(t *testing.T) {
	phone := types.NewJID("972502222222", types.DefaultUserServer)
	lid := types.NewJID("1234567890", types.HiddenUserServer)
	contacts := mockWatchUpContacts{byJID: map[string]types.ContactInfo{
		phone.String(): {Found: true, FirstName: "שמור דרך LID"},
	}}
	lids := &mockLIDStore{
		NoopStore: store.NoopStore{},
		lidByPN:   map[types.JID]types.JID{phone: lid},
		pnByLID:   map[types.JID]types.JID{lid: phone},
	}
	name, recognized := watchUpSavedContactFromStore(contacts, lids, lid)
	if !recognized || name != "שמור דרך LID" {
		t.Fatalf("LID lookup = %q %v", name, recognized)
	}
}

func TestWatchUpChatTypeFromJID(t *testing.T) {
	if got := watchUpChatTypeFromJID("status@broadcast"); got != "status" {
		t.Fatalf("status = %q", got)
	}
	if got := watchUpChatTypeFromJID("120363304995185034@g.us"); got != "group" {
		t.Fatalf("group = %q", got)
	}
	if got := watchUpChatTypeFromJID("972546561026@s.whatsapp.net"); got != "direct" {
		t.Fatalf("direct = %q", got)
	}
}
