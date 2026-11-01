"""Targeted tests for the human-confirmation gate (lot 1: tool security).

Unit tests use a dummy tool. Integration tests go through the real registry
and the real localFiles tool (skipped when the application is not importable).
"""
import threading
import time
from types import SimpleNamespace

import pytest

from jarvis.tools import confirmation
from jarvis.tools.base import Tool
from jarvis.tools.confirmation import Decision, Risk


@pytest.fixture(autouse=True)
def _reset_provider():
    confirmation.set_provider(None)
    yield
    confirmation.set_provider(None)


class Recorder(Tool):
    """Tool that records whether run() was reached."""

    def __init__(self, name):
        self._name = name
        self.ran = 0

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return "test"

    @property
    def inputSchema(self):
        return {"type": "object", "properties": {}}

    def run(self, args, context):
        from jarvis.tools.types import ToolExecutionResult
        self.ran += 1
        return ToolExecutionResult(success=True, reply_text="ok")


def _execute(tool, args):
    return tool.execute(
        db=None, cfg=None, tool_args=args, system_prompt="", original_prompt="",
        redacted_text="", max_retries=0, user_print=lambda _m: None,
    )


DELETE = {"operation": "delete", "path": "~/a.txt"}


@pytest.mark.unit
@pytest.mark.parametrize("operation,expected", [
    ("list", Risk.READ), ("search", Risk.READ), ("read", Risk.READ),
    ("READ ", Risk.READ),
    ("write", Risk.WRITE), ("append", Risk.WRITE),
    ("delete", Risk.DESTRUCTIVE), ("rename", Risk.DESTRUCTIVE),
    ("", Risk.DESTRUCTIVE),
])
def test_local_files_risk_by_operation(operation, expected):
    assert confirmation.classify("localFiles", {"operation": operation}) is expected


@pytest.mark.unit
def test_local_files_invalid_arguments_fail_closed():
    assert confirmation.classify("localFiles", None) is Risk.DESTRUCTIVE
    assert confirmation.classify("localFiles", ["delete"]) is Risk.DESTRUCTIVE
    assert confirmation.classify("localFiles", {"operation": 5}) is Risk.DESTRUCTIVE


@pytest.mark.unit
def test_other_tools_classification():
    assert confirmation.classify("getTime") is Risk.READ
    assert confirmation.classify("systemStatus") is Risk.READ
    assert confirmation.classify("deleteMeal") is Risk.DESTRUCTIVE
    assert confirmation.classify("logMeal") is Risk.WRITE
    assert confirmation.classify("screenshot") is Risk.PRIVACY
    assert confirmation.classify("srv__anything") is Risk.EXTERNAL
    assert confirmation.classify("unknownTool") is Risk.EXTERNAL


@pytest.mark.unit
def test_read_operation_needs_no_provider():
    tool = Recorder("localFiles")
    result = _execute(tool, {"operation": "list", "path": "~"})
    assert result.success is True and tool.ran == 1


@pytest.mark.unit
def test_sensitive_operation_blocked_without_provider():
    tool = Recorder("localFiles")
    result = _execute(tool, DELETE)
    assert result.success is False and tool.ran == 0
    assert result.missing_context == "confirmation"
    assert "aucune interface" in result.reply_text


@pytest.mark.unit
def test_denial_blocks_execution():
    confirmation.set_provider(lambda request: False)
    tool = Recorder("deleteMeal")
    result = _execute(tool, {"id": 1})
    assert result.success is False and tool.ran == 0
    assert "annul" in result.reply_text


@pytest.mark.unit
def test_approval_runs_tool_once():
    seen = []
    confirmation.set_provider(lambda request: seen.append(request) or True)
    tool = Recorder("localFiles")
    result = _execute(tool, {"operation": "write", "path": "~/a.txt", "content": "secret"})
    assert result.success is True and tool.ran == 1
    assert len(seen) == 1
    assert seen[0].risk is Risk.WRITE and seen[0].operation == "write"
    assert "a.txt" in seen[0].summary and "6 caract" in seen[0].summary
    assert "secret" not in seen[0].summary  # file content is never shown


@pytest.mark.unit
@pytest.mark.parametrize("answer", [None, "yes", 1, "True", 0])
def test_only_explicit_true_approves(answer):
    confirmation.set_provider(lambda request: answer)
    tool = Recorder("localFiles")
    result = _execute(tool, DELETE)
    assert result.success is False and tool.ran == 0


@pytest.mark.unit
def test_provider_exception_means_denied():
    def broken(request):
        raise RuntimeError("dialog crashed")
    confirmation.set_provider(broken)
    tool = Recorder("localFiles")
    result = _execute(tool, DELETE)
    assert result.success is False and tool.ran == 0


@pytest.mark.unit
def test_provider_timeout_expires_and_late_approval_is_ignored():
    release = threading.Event()

    def slow(request):
        release.wait(5)
        return True

    confirmation.set_provider(slow)
    started = time.monotonic()
    decision = confirmation.request_confirmation(
        "localFiles", DELETE, Risk.DESTRUCTIVE, timeout_sec=0.2,
    )
    release.set()
    assert decision is Decision.EXPIRED
    assert time.monotonic() - started < 2


@pytest.mark.unit
def test_each_call_needs_its_own_approval():
    calls = []
    confirmation.set_provider(lambda request: calls.append(request.request_id) or True)
    tool = Recorder("localFiles")
    _execute(tool, DELETE)
    _execute(tool, {"operation": "delete", "path": "~/b.txt"})
    assert len(calls) == 2 and len(set(calls)) == 2 and tool.ran == 2


@pytest.mark.unit
def test_expiry_sets_cancelled_event():
    seen = []

    def slow(request):
        seen.append(request)
        request.cancelled.wait(2)
        return True

    confirmation.set_provider(slow)
    decision = confirmation.request_confirmation(
        "localFiles", DELETE, Risk.DESTRUCTIVE, timeout_sec=0.1,
    )
    assert decision is Decision.EXPIRED
    assert seen and seen[0].cancelled.wait(1)


def _relay_answering(delay, approved, forced_id=None):
    box = {}

    def emit(request):
        def answer():
            time.sleep(delay)
            box["relay"].resolve(forced_id or request.request_id, approved)
        threading.Thread(target=answer, daemon=True).start()

    box["relay"] = confirmation.ConfirmationRelay(emit)
    return box["relay"]


@pytest.mark.unit
def test_relay_exact_request_id_approves():
    confirmation.set_provider(_relay_answering(0.05, True).provider)
    tool = Recorder("localFiles")
    result = _execute(tool, DELETE)
    assert result.success is True and tool.ran == 1


@pytest.mark.unit
def test_relay_answer_for_another_request_is_ignored():
    confirmation.set_provider(_relay_answering(0.05, True, "other-id").provider)
    started = time.monotonic()
    decision = confirmation.request_confirmation(
        "localFiles", DELETE, Risk.DESTRUCTIVE, timeout_sec=0.3,
    )
    assert decision is Decision.EXPIRED
    assert time.monotonic() - started < 2


@pytest.mark.unit
def test_relay_late_answer_after_expiry_is_invalid():
    ids = []
    relay = confirmation.ConfirmationRelay(lambda request: ids.append(request.request_id))
    confirmation.set_provider(relay.provider)
    decision = confirmation.request_confirmation(
        "localFiles", DELETE, Risk.DESTRUCTIVE, timeout_sec=0.1,
    )
    assert decision is Decision.EXPIRED
    assert relay.resolve(ids[0], True) is False


@pytest.mark.unit
def test_relay_answer_is_single_use_and_unknown_ids_rejected():
    ids = []
    relay = confirmation.ConfirmationRelay(lambda request: ids.append(request.request_id))
    confirmation.set_provider(relay.provider)
    result = {}

    def ask():
        result["decision"] = confirmation.request_confirmation(
            "localFiles", DELETE, Risk.DESTRUCTIVE, timeout_sec=2,
        )

    worker = threading.Thread(target=ask)
    worker.start()
    deadline = time.monotonic() + 2
    while not ids and time.monotonic() < deadline:
        time.sleep(0.01)
    assert relay.resolve("unknown", True) is False
    assert relay.resolve(ids[0], True) is True
    assert relay.resolve(ids[0], True) is False
    worker.join(2)
    assert result["decision"] is Decision.APPROVED


@pytest.mark.unit
def test_relay_emit_failure_means_denied():
    def broken_emit(request):
        raise OSError("pipe closed")

    confirmation.set_provider(confirmation.ConfirmationRelay(broken_emit).provider)
    tool = Recorder("localFiles")
    result = _execute(tool, DELETE)
    assert result.success is False and tool.ran == 0


@pytest.mark.unit
def test_new_relay_after_restart_has_no_pending_requests():
    assert confirmation.ConfirmationRelay(lambda request: None).resolve("any", True) is False


# ---------------------------------------------------------------- integration

def _run(name, args):
    from jarvis.tools.registry import run_tool_with_retries
    return run_tool_with_retries(
        db=None, cfg=SimpleNamespace(voice_debug=False, mcps={}), tool_name=name,
        tool_args=args, system_prompt="", original_prompt="", redacted_text="",
        max_retries=0,
    )


@pytest.fixture
def home(tmp_path, monkeypatch):
    pytest.importorskip("jarvis.tools.registry")
    local_files = pytest.importorskip("jarvis.tools.builtin.local_files")
    expanduser = local_files.os.path.expanduser
    monkeypatch.setattr(
        local_files.os.path, "expanduser",
        lambda path: str(tmp_path) if path == "~" else expanduser(path),
    )
    return tmp_path


@pytest.mark.unit
def test_registry_delete_denied_keeps_file(home):
    target = home / "keep.txt"
    target.write_text("data", encoding="utf-8")
    confirmation.set_provider(lambda request: False)
    result = _run("localFiles", {"operation": "delete", "path": "~/keep.txt"})
    assert result.success is False and target.exists()


@pytest.mark.unit
def test_registry_delete_without_provider_keeps_file(home):
    target = home / "keep.txt"
    target.write_text("data", encoding="utf-8")
    result = _run("localFiles", {"operation": "delete", "path": "~/keep.txt"})
    assert result.success is False and target.exists()


@pytest.mark.unit
def test_registry_delete_approved_removes_file(home):
    target = home / "gone.txt"
    target.write_text("data", encoding="utf-8")
    confirmation.set_provider(lambda request: True)
    result = _run("localFiles", {"operation": "delete", "path": "~/gone.txt"})
    assert result.success is True and not target.exists()


@pytest.mark.unit
def test_registry_write_denied_creates_nothing(home):
    result = _run("localFiles", {"operation": "write", "path": "~/new.txt", "content": "x"})
    assert result.success is False and not (home / "new.txt").exists()


@pytest.mark.unit
def test_registry_reads_need_no_confirmation(home):
    (home / "a.txt").write_text("hello", encoding="utf-8")
    listing = _run("localFiles", {"operation": "list", "path": "~", "glob": "*.txt"})
    assert listing.success is True and "a.txt" in listing.reply_text
    content = _run("localFiles", {"operation": "read", "path": "~/a.txt"})
    assert content.success is True and content.reply_text.strip() == "hello"
