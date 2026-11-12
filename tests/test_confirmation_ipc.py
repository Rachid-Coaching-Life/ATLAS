"""Confirmation wire protocol: strict parsing, exact-id answers, expiry notice."""
import json
import threading
import time

import pytest

from atlas.tools import confirmation
from atlas.tools import confirmation_ipc as ipc
from atlas.tools.confirmation import ConfirmationRelay, ConfirmationRequest, Decision, Risk

pytestmark = pytest.mark.unit

DELETE = {"operation": "delete", "path": "~/a.txt"}


@pytest.fixture(autouse=True)
def _reset_provider():
    confirmation.set_provider(None)
    yield
    confirmation.set_provider(None)


def make_request(**overrides):
    values = dict(request_id="abc123def456", tool="localFiles", operation="delete",
                  risk=Risk.DESTRUCTIVE, summary="localFiles : delete sur ~/a.txt",
                  timeout_sec=60.0)
    values.update(overrides)
    return ConfirmationRequest(**values)


def test_request_frame_round_trip_is_one_ascii_line():
    request = make_request(summary="Supprimer « café » \u2028 ligne")
    line = ipc.request_frame(request)
    assert line.startswith(ipc.REQUEST_PREFIX)
    assert "\n" not in line and "\r" not in line and line.isascii()
    assert len(line.splitlines()) == 1
    parsed = ipc.parse_request_frame(line)
    assert parsed["request_id"] == "abc123def456"
    assert parsed["risk"] == "destructive"
    assert parsed["summary"] == "Supprimer « café » \u2028 ligne"
    assert parsed["timeout_sec"] == 60.0


def test_oversized_summary_is_truncated_when_sent():
    parsed = ipc.parse_request_frame(ipc.request_frame(make_request(summary="x" * 5000)))
    assert len(parsed["summary"]) == ipc.MAX_SUMMARY_CHARS


def good_request_payload(**changes):
    payload = {"request_id": "abc123", "tool": "localFiles", "operation": "delete",
               "risk": "destructive", "summary": "ok", "timeout_sec": 60}
    payload.update(changes)
    return payload


@pytest.mark.parametrize("mutate", [
    lambda p: p.pop("summary"),
    lambda p: p.update(extra="x"),
    lambda p: p.update(request_id=""),
    lambda p: p.update(request_id="a" * 129),
    lambda p: p.update(request_id="bad id!"),
    lambda p: p.update(request_id=5),
    lambda p: p.update(risk="harmless"),
    lambda p: p.update(summary="x" * (ipc.MAX_SUMMARY_CHARS + 1)),
    lambda p: p.update(tool=None),
    lambda p: p.update(timeout_sec=0),
    lambda p: p.update(timeout_sec=-5),
    lambda p: p.update(timeout_sec=10_000),
    lambda p: p.update(timeout_sec=True),
    lambda p: p.update(timeout_sec="60"),
])
def test_malformed_request_frames_are_rejected(mutate):
    payload = good_request_payload()
    mutate(payload)
    assert ipc.parse_request_frame(ipc.REQUEST_PREFIX + json.dumps(payload)) is None


@pytest.mark.parametrize("line", [
    "", None, 5, "__CONFIRM__:", "__CONFIRM__:[]", "__CONFIRM__:not json",
    "  __CONFIRM__:{}", "Heard: __CONFIRM__:{}", "__CONFIRM_REPLY__:{}",
])
def test_garbage_is_not_a_request_frame(line):
    assert ipc.parse_request_frame(line) is None


def test_valid_payload_parses_and_leading_text_does_not():
    line = ipc.REQUEST_PREFIX + json.dumps(good_request_payload())
    assert ipc.parse_request_frame(line)["request_id"] == "abc123"
    assert ipc.parse_request_frame("x" + line) is None
    assert ipc.parse_request_frame(" " + line) is None


def test_cancel_frame_round_trip_and_strictness():
    line = ipc.cancel_frame(make_request())
    assert ipc.parse_cancel_frame(line) == "abc123def456"
    assert ipc.parse_cancel_frame(ipc.CANCEL_PREFIX + json.dumps({"request_id": "a", "x": 1})) is None
    assert ipc.parse_cancel_frame(ipc.CANCEL_PREFIX + json.dumps({"request_id": "bad id"})) is None
    assert ipc.parse_cancel_frame(" " + line) is None


def test_reply_round_trip_requires_a_real_boolean():
    assert ipc.parse_reply_line(ipc.reply_line("abc123", True)) == ("abc123", True)
    assert ipc.parse_reply_line(ipc.reply_line("abc123", False)) == ("abc123", False)
    for approved in ("true", "yes", 1, 0, None, "True", [True]):
        line = ipc.REPLY_PREFIX + json.dumps({"request_id": "abc123", "approved": approved})
        assert ipc.parse_reply_line(line) is None


@pytest.mark.parametrize("payload", [
    {"request_id": "abc123"},
    {"approved": True},
    {"request_id": "abc123", "approved": True, "extra": 1},
    {"request_id": "", "approved": True},
    {"request_id": "a" * 129, "approved": True},
    {"request_id": "bad id", "approved": True},
])
def test_malformed_replies_are_rejected(payload):
    assert ipc.parse_reply_line(ipc.REPLY_PREFIX + json.dumps(payload)) is None


def test_handle_reply_line_only_consumes_reply_lines():
    relay = ConfirmationRelay(lambda request: None)
    assert ipc.handle_reply_line(relay, "TASK:{}") is False
    assert ipc.handle_reply_line(relay, "") is False
    assert ipc.handle_reply_line(relay, None) is False
    assert ipc.handle_reply_line(relay, ipc.reply_line("zzz", True)) is True


def run_ask(timeout_sec=2.0):
    box = {}

    def ask():
        box["decision"] = confirmation.request_confirmation(
            "localFiles", DELETE, Risk.DESTRUCTIVE, timeout_sec=timeout_sec)

    worker = threading.Thread(target=ask)
    worker.start()
    return worker, box


def wait_for(predicate, seconds=2.0):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.01)
    return predicate()


def test_stdio_round_trip_approval_reaches_the_gate():
    written = []
    relay = ipc.make_stdio_relay(written.append)
    confirmation.set_provider(relay.provider)
    worker, box = run_ask()
    assert wait_for(lambda: len(written) == 1)
    request = ipc.parse_request_frame(written[0])
    assert request["risk"] == "destructive" and "a.txt" in request["summary"]
    assert ipc.handle_reply_line(relay, ipc.reply_line(request["request_id"], True))
    worker.join(2)
    assert box["decision"] is Decision.APPROVED
    assert len(written) == 1  # no cancel notice after an answer


def test_stdio_refusal_and_wrong_id_and_replay():
    written = []
    relay = ipc.make_stdio_relay(written.append)
    confirmation.set_provider(relay.provider)
    worker, box = run_ask(timeout_sec=0.4)
    assert wait_for(lambda: len(written) == 1)
    request_id = ipc.parse_request_frame(written[0])["request_id"]
    ipc.handle_reply_line(relay, ipc.reply_line("another-id", True))
    worker.join(2)
    assert box["decision"] is Decision.EXPIRED
    assert ipc.handle_reply_line(relay, ipc.reply_line(request_id, True)) is True
    assert relay.resolve(request_id, True) is False


def test_explicit_no_is_a_denial():
    written = []
    relay = ipc.make_stdio_relay(written.append)
    confirmation.set_provider(relay.provider)
    worker, box = run_ask()
    assert wait_for(lambda: len(written) == 1)
    request_id = ipc.parse_request_frame(written[0])["request_id"]
    ipc.handle_reply_line(relay, ipc.reply_line(request_id, False))
    worker.join(2)
    assert box["decision"] is Decision.DENIED


def test_expiry_sends_one_cancel_frame_and_refuses():
    written = []
    relay = ipc.make_stdio_relay(written.append)
    confirmation.set_provider(relay.provider)
    worker, box = run_ask(timeout_sec=0.2)
    worker.join(3)
    assert box["decision"] is Decision.EXPIRED
    assert wait_for(lambda: len(written) == 2)
    request_id = ipc.parse_request_frame(written[0])["request_id"]
    assert ipc.parse_cancel_frame(written[1]) == request_id
    time.sleep(0.2)
    assert len(written) == 2


def test_malformed_reply_leaves_the_request_to_expire_and_be_refused():
    written = []
    relay = ipc.make_stdio_relay(written.append)
    confirmation.set_provider(relay.provider)
    worker, box = run_ask(timeout_sec=0.4)
    assert wait_for(lambda: len(written) == 1)
    request_id = ipc.parse_request_frame(written[0])["request_id"]
    bad = ipc.REPLY_PREFIX + json.dumps({"request_id": request_id, "approved": "true"})
    assert ipc.handle_reply_line(relay, bad) is True
    worker.join(3)
    assert box["decision"] is Decision.EXPIRED


def test_lost_pipe_means_denied_without_cancel_notice():
    notices = []

    def broken_write(line):
        raise BrokenPipeError("daemon stdout closed")

    relay = ConfirmationRelay(
        emit=lambda request: broken_write(ipc.request_frame(request)),
        on_expire=notices.append,
    )
    confirmation.set_provider(relay.provider)
    worker, box = run_ask()
    worker.join(2)
    assert box["decision"] is Decision.DENIED
    assert notices == []


def test_expiry_notice_failure_is_ignored():
    def explode(request):
        raise RuntimeError("ui gone")

    relay = ConfirmationRelay(lambda request: None, on_expire=explode)
    confirmation.set_provider(relay.provider)
    worker, box = run_ask(timeout_sec=0.2)
    worker.join(3)
    assert box["decision"] is Decision.EXPIRED


def test_relay_without_expiry_hook_still_works_as_before():
    relay = ConfirmationRelay(lambda request: None)
    confirmation.set_provider(relay.provider)
    worker, box = run_ask(timeout_sec=0.2)
    worker.join(3)
    assert box["decision"] is Decision.EXPIRED


def test_answer_right_after_broker_expiry_is_refused_immediately():
    ids = []
    relay = ConfirmationRelay(lambda request: ids.append(request.request_id))
    confirmation.set_provider(relay.provider)
    decision = confirmation.request_confirmation(
        "localFiles", DELETE, Risk.DESTRUCTIVE, timeout_sec=0.1)
    assert decision is Decision.EXPIRED
    assert relay.resolve(ids[0], True) is False


def test_expired_decision_label_is_stable():
    for _ in range(5):
        relay = ConfirmationRelay(lambda request: None)
        confirmation.set_provider(relay.provider)
        decision = confirmation.request_confirmation(
            "localFiles", DELETE, Risk.DESTRUCTIVE, timeout_sec=0.1)
        assert decision is Decision.EXPIRED
