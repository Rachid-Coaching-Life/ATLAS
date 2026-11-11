"""Wire format for confirmation requests between the daemon and the desktop UI.

Used when the tools run in a child process and the confirmation dialog lives
in the desktop application. Three single-line frames, always ASCII (so no
line splitter can cut one) and always starting at the first character of the
line:

* daemon -> UI, stdout: ``__CONFIRM__:{...}`` a request to show;
* daemon -> UI, stdout: ``__CONFIRM_CANCEL__:{...}`` the request expired;
* UI -> daemon, stdin: ``__CONFIRM_REPLY__:{...}`` the user's explicit answer.

Parsing is strict: wrong prefix, leading text, unknown or missing fields,
wrong types, oversized values -> the line is ignored. The daemon is the
authority: it expires and refuses on its own, and it accepts an answer only
for the exact pending request, once (see ``ConfirmationRelay``).
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Optional, Tuple

from .confirmation import ConfirmationRelay, ConfirmationRequest, Risk

REQUEST_PREFIX = "__CONFIRM__:"
CANCEL_PREFIX = "__CONFIRM_CANCEL__:"
REPLY_PREFIX = "__CONFIRM_REPLY__:"

MAX_SUMMARY_CHARS = 400
MAX_FIELD_CHARS = 128
MAX_TIMEOUT_SEC = 300.0

_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_REQUEST_KEYS = frozenset(
    {"request_id", "tool", "operation", "risk", "summary", "timeout_sec"}
)
_RISKS = frozenset(risk.value for risk in Risk)


def _dump(prefix: str, payload: Dict[str, Any]) -> str:
    return prefix + json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def _load(line: Any, prefix: str) -> Optional[Dict[str, Any]]:
    if not isinstance(line, str) or not line.startswith(prefix):
        return None
    try:
        data = json.loads(line[len(prefix):])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def request_frame(request: ConfirmationRequest) -> str:
    """Daemon -> UI: the request to display (summary is length-bounded)."""
    return _dump(REQUEST_PREFIX, {
        "request_id": request.request_id,
        "tool": request.tool[:MAX_FIELD_CHARS],
        "operation": request.operation[:MAX_FIELD_CHARS],
        "risk": request.risk.value,
        "summary": request.summary[:MAX_SUMMARY_CHARS],
        "timeout_sec": request.timeout_sec,
    })


def cancel_frame(request: ConfirmationRequest) -> str:
    """Daemon -> UI: this request expired, close its dialog."""
    return _dump(CANCEL_PREFIX, {"request_id": request.request_id})


def reply_line(request_id: str, approved: bool) -> str:
    """UI -> daemon: the user's answer for one exact request."""
    return _dump(REPLY_PREFIX, {"request_id": request_id, "approved": bool(approved)})


def parse_request_frame(line: Any) -> Optional[Dict[str, Any]]:
    """Return the validated request fields, or None for anything else."""
    data = _load(line, REQUEST_PREFIX)
    if data is None or set(data) != _REQUEST_KEYS:
        return None
    if not _valid_id(data["request_id"]):
        return None
    for key in ("tool", "operation"):
        if not isinstance(data[key], str) or len(data[key]) > MAX_FIELD_CHARS:
            return None
    if data["risk"] not in _RISKS:
        return None
    if not isinstance(data["summary"], str) or len(data["summary"]) > MAX_SUMMARY_CHARS:
        return None
    timeout = data["timeout_sec"]
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        return None
    if not 0 < timeout <= MAX_TIMEOUT_SEC:
        return None
    return dict(data)


def parse_cancel_frame(line: Any) -> Optional[str]:
    """Return the expired request identifier, or None."""
    data = _load(line, CANCEL_PREFIX)
    if data is None or set(data) != {"request_id"} or not _valid_id(data["request_id"]):
        return None
    return data["request_id"]


def parse_reply_line(line: Any) -> Optional[Tuple[str, bool]]:
    """Return (request_id, approved) for a strictly valid reply, or None."""
    data = _load(line, REPLY_PREFIX)
    if data is None or set(data) != {"request_id", "approved"}:
        return None
    if not _valid_id(data["request_id"]) or type(data["approved"]) is not bool:
        return None
    return data["request_id"], data["approved"]


def handle_reply_line(relay: ConfirmationRelay, line: Any) -> bool:
    """Daemon stdin handler. True when the line was a confirmation reply.

    A valid reply is passed to the relay (which accepts it only for the exact
    pending request, once). A malformed reply is consumed and ignored: the
    request then expires and is refused.
    """
    if not isinstance(line, str) or not line.startswith(REPLY_PREFIX):
        return False
    parsed = parse_reply_line(line)
    if parsed is not None:
        relay.resolve(*parsed)
    return True


def make_stdio_relay(write_line: Callable[[str], None]) -> ConfirmationRelay:
    """Relay for a daemon whose UI reads stdout and answers on stdin.

    ``write_line`` must write one line to stdout, flush it, and be safe to
    call from several threads. Register ``relay.provider`` with
    ``confirmation.set_provider`` and route stdin lines to
    ``handle_reply_line(relay, line)``.
    """
    return ConfirmationRelay(
        emit=lambda request: write_line(request_frame(request)),
        on_expire=lambda request: write_line(cancel_frame(request)),
    )
