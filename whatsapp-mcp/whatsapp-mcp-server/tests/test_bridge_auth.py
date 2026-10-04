import importlib

import main
import whatsapp


def test_bridge_headers_uses_env_token(monkeypatch):
    monkeypatch.setenv("WHATSAPP_BRIDGE_TOKEN", "env-token")

    assert whatsapp._bridge_headers() == {"Authorization": "Bearer env-token"}


def test_bridge_headers_falls_back_to_token_file(monkeypatch, tmp_path):
    token_file = tmp_path / ".bridge-token"
    token_file.write_text("file-token\n", encoding="utf-8")
    monkeypatch.delenv("WHATSAPP_BRIDGE_TOKEN", raising=False)
    monkeypatch.setattr(whatsapp, "_BRIDGE_TOKEN_PATH", str(token_file))

    assert whatsapp._bridge_headers() == {"Authorization": "Bearer file-token"}


def test_bridge_headers_reads_token_next_to_whatsmeow_db_path(monkeypatch, tmp_path):
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    (store_dir / ".bridge-token").write_text("volume-token\n", encoding="utf-8")

    monkeypatch.delenv("WHATSAPP_BRIDGE_TOKEN", raising=False)
    monkeypatch.setenv("WHATSMEOW_DB_PATH", str(store_dir / "whatsapp.db"))

    try:
        importlib.reload(whatsapp)
        assert whatsapp._bridge_headers() == {"Authorization": "Bearer volume-token"}
    finally:
        monkeypatch.delenv("WHATSMEOW_DB_PATH", raising=False)
        importlib.reload(whatsapp)


def test_bridge_headers_prefers_env_over_token_file(monkeypatch, tmp_path):
    token_file = tmp_path / ".bridge-token"
    token_file.write_text("file-token\n", encoding="utf-8")
    monkeypatch.setenv("WHATSAPP_BRIDGE_TOKEN", "env-token")
    monkeypatch.setattr(whatsapp, "_BRIDGE_TOKEN_PATH", str(token_file))

    assert whatsapp._bridge_headers() == {"Authorization": "Bearer env-token"}


def test_outbound_helpers_refuse_without_calling_bridge(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("outbound helper must not call the bridge")

    monkeypatch.setattr(whatsapp.requests, "post", fake_post)

    helpers = [
        (whatsapp.send_message, ("12025551234", "hello")),
        (whatsapp.send_file, ("12025551234", "/tmp/file.jpg")),
        (whatsapp.send_audio_message, ("12025551234", "/tmp/file.ogg")),
        (whatsapp.send_reaction, ("12025551234@s.whatsapp.net", "message-id", "👍")),
    ]
    for helper, args in helpers:
        success, message = helper(*args)
        assert success is False
        assert message == "Outbound WhatsApp actions are disabled: this connection is read-only."

    assert calls == []


def test_mcp_does_not_expose_outbound_tools():
    for name in ("send_message", "send_file", "send_audio_message", "send_reaction"):
        assert not hasattr(main, name)
