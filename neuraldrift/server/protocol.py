"""NeuralDrift protocol — JSON Lines message encode/decode over Unix socket."""

import json
import time
import uuid


def _make_id() -> str:
    return f"req-{uuid.uuid4().hex[:8]}"


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ── Encode ────────────────────────────────────────────────────────────

def encode_request(method: str, params: dict | None = None, req_id: str | None = None) -> bytes:
    """Client → Server request as JSON line."""
    msg = {
        "id": req_id or _make_id(),
        "method": method,
        "params": params or {},
    }
    return json.dumps(msg, separators=(",", ":")).encode() + b"\n"


def encode_response(req_id: str, result=None, error: str | None = None) -> bytes:
    """Server → Client response as JSON line."""
    msg = {"id": req_id, "type": "response"}
    if error:
        msg["ok"] = False
        msg["error"] = error
    else:
        msg["ok"] = True
        msg["result"] = result
    return json.dumps(msg, separators=(",", ":")).encode() + b"\n"


def encode_event(event: str, data: dict | None = None) -> bytes:
    """Server → Client push event as JSON line."""
    msg = {
        "type": "event",
        "event": event,
        "data": data or {},
        "ts": _ts(),
    }
    return json.dumps(msg, separators=(",", ":")).encode() + b"\n"


# ── Decode ────────────────────────────────────────────────────────────

def decode_message(line: bytes | str) -> dict | None:
    """Parse a JSON line into a message dict. Returns None on bad input."""
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None
