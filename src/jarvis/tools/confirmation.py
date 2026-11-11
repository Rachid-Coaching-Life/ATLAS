"""Human-confirmation gate for sensitive tool operations.

Fail-closed policy: a sensitive operation runs only after an explicit
approval returned by a registered confirmation provider. Without a provider,
with a refusal, an error, an invalid timeout or a timeout, the operation is
NOT executed.

The gate is independent of any GUI toolkit. The desktop application registers
a provider with ``set_provider``; the provider shows the request to the user
(on the right thread) and returns True only for an explicit approval.
A language model can never grant a confirmation: nothing in the prompt or in
a tool argument influences the decision.
"""
from __future__ import annotations

import math
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..debug import debug_log
from .local_paths import describe_target
from .types import ToolExecutionResult

DEFAULT_TIMEOUT_SEC = 60.0
# Longest delay the wire protocol accepts (see confirmation_ipc.MAX_TIMEOUT_SEC).
MAX_TIMEOUT_SEC = 300.0
_RELAY_POLL_SEC = 0.05
_RELAY_EXPIRY_GRACE_SEC = 1.0
_SUMMARY_VALUE_LIMIT = 80
_SUMMARY_KEY_LIMIT = 30
_SUMMARY_MAX_ARGS = 5
# Must stay <= confirmation_ipc.MAX_SUMMARY_CHARS so the frame never cuts it.
_SUMMARY_MAX_CHARS = 400
_SUMMARY_NOTICE_RESERVE = 60
_PATH_KEYS = frozenset(
    {"path", "file", "filename", "source", "destination", "target"}
)


class Risk(str, Enum):
    READ = "read"
    NETWORK = "network"
    PRIVACY = "privacy"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    EXTERNAL = "external"


# Risks that need an explicit human decision before execution.
CONFIRMED_RISKS = frozenset(
    {Risk.PRIVACY, Risk.WRITE, Risk.DESTRUCTIVE, Risk.EXTERNAL}
)


class Decision(str, Enum):
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"  # invalid request parameters: refused, nothing asked


@dataclass(frozen=True)
class ConfirmationRequest:
    request_id: str
    tool: str
    operation: str
    risk: Risk
    summary: str
    timeout_sec: float
    # Set when the request expires: a UI should close its dialog.
    cancelled: threading.Event = field(
        default_factory=threading.Event, compare=False, repr=False
    )


# A provider returns True only for an explicit approval. It may block until
# the user answers; the broker enforces the timeout itself.
Provider = Callable[[ConfirmationRequest], bool]

_provider: Optional[Provider] = None
_provider_lock = threading.Lock()


def set_provider(provider: Optional[Provider]) -> None:
    """Register (or clear with None) the interface that asks the user."""
    global _provider
    with _provider_lock:
        _provider = provider


def get_provider() -> Optional[Provider]:
    with _provider_lock:
        return _provider


class ConfirmationRelay:
    """Bridge for a UI living in another thread or process.

    ``provider`` is registered with ``set_provider``. It publishes the request
    through ``emit`` (a Qt signal, an IPC line...) and waits. The UI answers
    with ``resolve(request_id, approved)``. An answer counts only for the exact
    pending request, once, before expiry. Unknown, expired or repeated
    identifiers are ignored. Nothing is persisted, so a restart of the
    process invalidates every pending request. A failing ``emit`` means "no".

    The broker's clock is authoritative: when it expires a request it sets
    ``request.cancelled``, and from that instant every answer is refused.
    The relay notices within ``_RELAY_POLL_SEC`` (and in any case stops
    waiting a grace period after the timeout, as a safety net).

    ``on_expire`` (optional) is called once, with the request, when no answer
    arrived in time, so the UI can close its dialog. It is never called when
    the request was answered or when ``emit`` failed, and its own failures
    are ignored.
    """

    def __init__(
        self,
        emit: Callable[[ConfirmationRequest], None],
        on_expire: Optional[Callable[[ConfirmationRequest], None]] = None,
    ) -> None:
        self._emit = emit
        self._on_expire = on_expire
        self._lock = threading.Lock()
        self._pending: Dict[str, Dict[str, Any]] = {}

    def provider(self, request: ConfirmationRequest) -> bool:
        slot: Dict[str, Any] = {
            "event": threading.Event(), "approved": False, "request": request,
        }
        with self._lock:
            self._pending[request.request_id] = slot
        try:
            self._emit(request)
            deadline = time.monotonic() + request.timeout_sec + _RELAY_EXPIRY_GRACE_SEC
            while not slot["event"].wait(_RELAY_POLL_SEC):
                if request.cancelled.is_set() or time.monotonic() >= deadline:
                    with self._lock:
                        self._pending.pop(request.request_id, None)
                    self._notify_expired(request)
                    return False
            return slot["approved"] is True
        except Exception as exc:
            debug_log(f"confirmation relay failed ({type(exc).__name__})", "tools")
            return False
        finally:
            with self._lock:
                self._pending.pop(request.request_id, None)

    def _notify_expired(self, request: ConfirmationRequest) -> None:
        if self._on_expire is None:
            return
        try:
            self._on_expire(request)
        except Exception as exc:
            debug_log(f"confirmation expiry notice failed ({type(exc).__name__})", "tools")

    def resolve(self, request_id: str, approved: bool) -> bool:
        """Record the user's answer; False if the request is not pending."""
        with self._lock:
            slot = self._pending.pop(request_id, None)
        if slot is None or slot["request"].cancelled.is_set():
            return False
        slot["approved"] = approved is True
        slot["event"].set()
        return True


_LOCAL_FILES_READ = frozenset({"list", "search", "read"})
_LOCAL_FILES_WRITE = frozenset({"write", "append"})

# Builtin tools. Anything not listed is treated as EXTERNAL (fail-closed).
_BUILTIN_RISK: Dict[str, Risk] = {
    "getTime": Risk.READ,
    "systemStatus": Risk.READ,
    "stop": Risk.READ,
    "toolSearchTool": Risk.READ,
    "fetchMeals": Risk.READ,
    "webSearch": Risk.NETWORK,
    "fetchWebPage": Risk.NETWORK,
    "getWeather": Risk.NETWORK,
    "screenshot": Risk.PRIVACY,
    "logMeal": Risk.WRITE,
    "deleteMeal": Risk.DESTRUCTIVE,
    "refreshMCPTools": Risk.EXTERNAL,
}


def _local_files_operation(args: Any) -> str:
    if isinstance(args, dict):
        return str(args.get("operation") or "").strip().lower()
    return ""


def classify(tool_name: Optional[str], args: Any = None) -> Risk:
    """Return the risk of calling ``tool_name`` with ``args``."""
    name = (tool_name or "").strip()
    if "__" in name:  # server__tool: external MCP tool, effects unknown
        return Risk.EXTERNAL
    if name == "localFiles":
        operation = _local_files_operation(args)
        if operation in _LOCAL_FILES_READ:
            return Risk.READ
        if operation in _LOCAL_FILES_WRITE:
            return Risk.WRITE
        return Risk.DESTRUCTIVE  # delete and any unknown operation
    return _BUILTIN_RISK.get(name, Risk.EXTERNAL)


def _clean(text: Any) -> str:
    """Make text safe to show in a dialog.

    Line/paragraph separators and control characters (category Cc, Zl, Zp)
    become a space; invisible format characters (category Cf: bidirectional
    controls, zero-width characters...) are removed.
    """
    out: List[str] = []
    for char in str(text):
        category = unicodedata.category(char)
        if category in ("Cc", "Zl", "Zp"):
            out.append(" ")
        elif category != "Cf":
            out.append(char)
    return "".join(out)


def _short(value: Any, keep_end: bool = False, limit: int = _SUMMARY_VALUE_LIMIT) -> str:
    # Bound Unicode scanning before sanitising long JSON-derived values.
    raw = str(value)
    if len(raw) <= limit:
        return _clean(raw)
    if keep_end:  # the end of a path (file name) is what matters
        return "…" + _clean(raw[-limit:])
    return _clean(raw[:limit]) + "…"


def _omitted_notice(count: int) -> str:
    return f" (+{count} argument{'s' if count > 1 else ''} non affiché{'s' if count > 1 else ''})"


def summarize(tool_name: str, args: Any) -> str:
    """Describe the action for the user. File contents are never included.

    The text is sanitised, bounded by ``_SUMMARY_MAX_CHARS`` and states how
    many arguments are not shown. For ``localFiles`` the target is resolved
    with the rules of the tool itself and shown after an arrow whenever it
    differs from the path as given (relative path, ``..``, absolute form), or
    marked as refused when the tool will not act on it.
    """
    name = _short(tool_name, limit=_SUMMARY_KEY_LIMIT * 2)
    if tool_name == "localFiles" and isinstance(args, dict):
        operation_name = _local_files_operation(args)
        operation = _short(operation_name or "?")
        given = args.get("path", "?")
        text = f"localFiles : {operation} sur {_short(given, keep_end=True)}"
        target = describe_target(operation_name, given)
        if target and target != given:
            # Refusals must retain their leading warning, even for long paths.
            refused = target.startswith("[refusé")
            text += f" → {_short(target, keep_end=not refused, limit=100)}"
        content = args.get("content")
        if isinstance(content, str):
            text += f" ({len(content)} caractères)"
        hidden = len([k for k in args if k not in ("operation", "path", "content")])
        if hidden:
            text += _omitted_notice(hidden)
        return text[:_SUMMARY_MAX_CHARS]
    if isinstance(args, dict) and args:
        parts: List[str] = []
        used = len(name) + 3
        budget = _SUMMARY_MAX_CHARS - _SUMMARY_NOTICE_RESERVE
        for key, value in args.items():
            key_text = _short(key, limit=_SUMMARY_KEY_LIMIT)
            part = f"{key_text}={_short(value, keep_end=key_text in _PATH_KEYS)}"
            if len(parts) >= _SUMMARY_MAX_ARGS or used + len(part) + 2 > budget:
                break
            parts.append(part)
            used += len(part) + 2
        hidden = len(args) - len(parts)
        text = f"{name} ({', '.join(parts)})" if parts else name
        if hidden:
            text += _omitted_notice(hidden)
        return text[:_SUMMARY_MAX_CHARS]
    return name


def _valid_timeout(value: Any) -> Optional[float]:
    """Return the timeout as a float, or None when it must be refused."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        timeout = float(value)
    except (OverflowError, ValueError, TypeError):
        return None
    if not math.isfinite(timeout) or not 0 < timeout <= MAX_TIMEOUT_SEC:
        return None
    return timeout


def request_confirmation(
    tool_name: str,
    args: Any,
    risk: Risk,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> Decision:
    """Ask the registered provider and return the decision (never raises).

    A timeout that is not a finite number in ]0, MAX_TIMEOUT_SEC] is refused
    at once (``Decision.INVALID``): nothing is asked and nothing is clamped.
    """
    timeout = _valid_timeout(timeout_sec)
    if timeout is None:
        debug_log("confirmation refused: invalid timeout", "tools")
        return Decision.INVALID
    provider = get_provider()
    if provider is None:
        return Decision.UNAVAILABLE
    try:
        request = ConfirmationRequest(
            request_id=uuid.uuid4().hex[:12],
            tool=_clean(str(tool_name)),
            operation=_clean(_local_files_operation(args)) if tool_name == "localFiles" else "",
            risk=risk,
            summary=summarize(str(tool_name), args),
            timeout_sec=timeout,
        )
    except Exception as exc:
        # Malformed argument representations must never reach an approval UI.
        debug_log(f"confirmation summary refused ({type(exc).__name__})", "tools")
        return Decision.INVALID
    outcome: Dict[str, Any] = {}
    finished = threading.Event()

    def _ask() -> None:
        try:
            outcome["approved"] = provider(request) is True
        except Exception as exc:  # a failing interface means "no"
            debug_log(f"confirmation provider failed ({type(exc).__name__})", "tools")
            outcome["approved"] = False
        finally:
            finished.set()

    threading.Thread(target=_ask, name="atlas-confirmation", daemon=True).start()
    if not finished.wait(timeout):
        request.cancelled.set()
        decision = Decision.EXPIRED
    else:
        decision = Decision.APPROVED if outcome.get("approved") else Decision.DENIED
    debug_log(
        f"confirmation {request.request_id}: tool={request.tool} "
        f"risk={risk.value} decision={decision.value}",
        "tools",
    )
    return decision


_MESSAGES = {
    Decision.DENIED: "Action annulée : vous n'avez pas confirmé. Rien n'a été exécuté.",
    Decision.EXPIRED: "Action annulée : aucune confirmation reçue à temps. Rien n'a été exécuté.",
    Decision.UNAVAILABLE: (
        "Action non exécutée : aucune interface de confirmation n'est disponible."
    ),
    Decision.INVALID: (
        "Action non exécutée : délai de confirmation invalide. Rien n'a été exécuté."
    ),
}


def gate(
    tool_name: str,
    args: Any,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> Optional[ToolExecutionResult]:
    """Return None to let the tool run, or a failure result when blocked."""
    risk = classify(tool_name, args)
    if risk not in CONFIRMED_RISKS:
        return None
    decision = request_confirmation(tool_name, args, risk, timeout_sec)
    if decision is Decision.APPROVED:
        return None
    message = _MESSAGES[decision]
    return ToolExecutionResult(
        success=False,
        reply_text=message,
        error_message=message,
        missing_context="confirmation",
    )
