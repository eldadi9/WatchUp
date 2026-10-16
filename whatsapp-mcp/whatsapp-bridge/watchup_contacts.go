package main

import (
	"context"
	"strings"

	"go.mau.fi/whatsmeow/types"
)

type watchUpContactSource interface {
	GetContact(context.Context, types.JID) (types.ContactInfo, error)
}

type watchUpLIDSource interface {
	GetPNForLID(context.Context, types.JID) (types.JID, error)
	GetLIDForPN(context.Context, types.JID) (types.JID, error)
}

func watchUpLocalContactName(info types.ContactInfo) string {
	for _, value := range []string{info.FullName, info.FirstName, info.BusinessName} {
		if name := strings.TrimSpace(value); name != "" {
			return name
		}
	}
	return ""
}

func watchUpChatType(chat types.JID) string {
	if chat.IsEmpty() {
		return "direct"
	}
	return watchUpChatTypeFromJID(chat.String())
}

func watchUpChatTypeFromJID(chatJID string) string {
	jid, err := types.ParseJID(strings.TrimSpace(chatJID))
	if err != nil || jid.IsEmpty() {
		return "direct"
	}
	switch jid.Server {
	case types.GroupServer:
		return "group"
	case "newsletter":
		return "newsletter"
	case "broadcast":
		if jid.User == "status" {
			return "status"
		}
		return "broadcast"
	default:
		return "direct"
	}
}

func watchUpContactLookupJIDs(jid types.JID, lids watchUpLIDSource) []types.JID {
	seen := map[string]struct{}{}
	var out []types.JID
	add := func(candidate types.JID) {
		if candidate.IsEmpty() {
			return
		}
		candidate = candidate.ToNonAD()
		key := candidate.String()
		if _, exists := seen[key]; exists {
			return
		}
		seen[key] = struct{}{}
		out = append(out, candidate)
	}
	add(jid)
	if lids == nil {
		return out
	}
	ctx := context.Background()
	normalized := jid.ToNonAD()
	if normalized.Server == types.HiddenUserServer {
		if phone, err := lids.GetPNForLID(ctx, normalized); err == nil {
			add(phone)
		}
	}
	if normalized.Server == types.DefaultUserServer {
		if lid, err := lids.GetLIDForPN(ctx, normalized); err == nil {
			add(lid)
		}
	}
	return out
}

func watchUpSavedContactFromStore(contacts watchUpContactSource, lids watchUpLIDSource, jid types.JID) (string, bool) {
	if contacts == nil || jid.IsEmpty() {
		return "", false
	}
	for _, candidate := range watchUpContactLookupJIDs(jid, lids) {
		info, err := contacts.GetContact(context.Background(), candidate)
		if err != nil || !info.Found {
			continue
		}
		if name := watchUpLocalContactName(info); name != "" {
			return name, true
		}
	}
	return "", false
}
