"""Hardening of the confirmation gate: timeout validation and safe summaries."""
import math
import threading

import pytest

from jarvis.tools import confirmation
from jarvis.tools import confirmation_ipc as ipc
from jarvis.tools.confirmation import ConfirmationRelay, Decision, Risk

pytestmark = pytest.mark.unit

DELETE = {"operation": "delete", "path": "~/a.txt"}


@pytest.fixture(autouse=True)
def _reset_provider():
    confirmation.set_provider(None)
    yield
    confirmation.set_provider(None)


def test_timeout_limits_match_the_wire_protocol():
    assert confirmation.MAX_TIMEOUT_SEC == ipc.MAX_TIMEOUT_SEC
    assert confirmation._SUMMARY_MAX_CHARS <= ipc.MAX_SUMMARY_CHARS


@pytest.mark.parametrize("timeout", [
    math.inf, -math.inf, math.nan, -1, -0.001, 0, 0.0, 300.001, 301, 1e12,
    True, False, None, "60", [60],
])
def test_invalid_timeout_is_refused_without_asking(timeout):
    asked = []
    confirmation.set_provider(lambda request: asked.append(request) or True)
    decision = confirmation.request_confirmation(
        "localFiles", DELETE, Risk.DESTRUCTIVE, timeout_sec=timeout)
    assert decision is Decision.INVALID
    assert asked == []


@pytest.mark.parametrize("timeout", [math.inf, math.nan, 0, 301])
def test_gate_blocks_the_tool_on_invalid_timeout(timeout):
    confirmation.set_provider(lambda request: True)
    result = confirmation.gate("localFiles", DELETE, timeout_sec=timeout)
    assert result is not None and result.success is False
    assert result.missing_context == "confirmation"
    assert "invalide" in result.reply_text


def test_invalid_timeout_without_provider_is_still_refused():
    result = confirmation.gate("localFiles", DELETE, timeout_sec=math.inf)
    assert result is not None and result.success is False


def test_timeout_is_never_clamped():
    seen = []
    confirmation.set_provider(lambda request: seen.append(request) or True)
    assert confirmation.request_confirmation(
        "localFiles", DELETE, Risk.DESTRUCTIVE, timeout_sec=300) is Decision.APPROVED
    assert seen[0].timeout_sec == 300.0
    assert confirmation.request_confirmation(
        "localFiles", DELETE, Risk.DESTRUCTIVE, timeout_sec=1000) is Decision.INVALID
    assert len(seen) == 1


def test_valid_integer_timeout_is_accepted_as_float():
    seen = []
    confirmation.set_provider(lambda request: seen.append(request) or True)
    assert confirmation.request_confirmation(
        "localFiles", DELETE, Risk.DESTRUCTIVE, timeout_sec=5) is Decision.APPROVED
    assert seen[0].timeout_sec == 5.0 and isinstance(seen[0].timeout_sec, float)


def test_default_timeout_is_accepted_by_the_wire_parser():
    request = {}
    confirmation.set_provider(lambda r: request.setdefault("r", r) and True)
    confirmation.request_confirmation("localFiles", DELETE, Risk.DESTRUCTIVE)
    assert 0 < request["r"].timeout_sec <= ipc.MAX_TIMEOUT_SEC


def test_pending_request_never_exceeds_the_protocol_limit():
    ids = []
    relay = ConfirmationRelay(lambda request: ids.append(request))
    confirmation.set_provider(relay.provider)
    worker = threading.Thread(target=lambda: confirmation.request_confirmation(
        "localFiles", DELETE, Risk.DESTRUCTIVE, timeout_sec=0.2))
    worker.start()
    worker.join(3)
    assert ids and ids[0].timeout_sec <= ipc.MAX_TIMEOUT_SEC


# ------------------------------------------------------------------ summaries

HOSTILE = "a\rb\x00c\x1bd\u202ee\u2066f\u200bg\u2028h\u2029i\x85j\tk\nl"


@pytest.mark.parametrize("char", ["\r", "\n", "\t", "\x00", "\x1b", "\x85",
                                  "\u2028", "\u2029", "\u202e", "\u202a",
                                  "\u2066", "\u2069", "\u200e", "\u200f", "\u200b"])
def test_control_and_bidi_characters_never_reach_the_summary(char):
    summary = confirmation.summarize("localFiles", {
        "operation": "write", "path": f"~/x{char}y.txt", "content": "z"})
    assert all(ord(c) >= 32 and c not in "\x7f\x85\u2028\u2029" for c in summary)
    assert not any(c in summary for c in "\u202e\u202a\u2066\u2069\u200e\u200f\u200b")


def test_hostile_text_is_neutralised_in_every_field():
    summary = confirmation.summarize("tool\u202e\r", {HOSTILE: HOSTILE})
    for char in "\r\n\t\x00\x1b\x85\u2028\u2029\u202e\u2066\u200b":
        assert char not in summary
    assert "ab" in summary or "a b" in summary


def test_request_fields_are_sanitised():
    seen = []
    confirmation.set_provider(lambda request: seen.append(request) or True)
    confirmation.request_confirmation(
        "localFiles", {"operation": "wri\u202ete\r", "path": "~/a"}, Risk.WRITE)
    request = seen[0]
    assert request.tool == "localFiles"
    assert "\u202e" not in request.operation and "\r" not in request.operation
    assert "\u202e" not in request.summary


def test_normal_text_with_accents_is_preserved():
    summary = confirmation.summarize("localFiles", {
        "operation": "write", "path": "~/Documents/café été.txt", "content": "abc"})
    assert "café été.txt" in summary and "3 caractères" in summary


def test_long_path_keeps_its_end_for_local_files():
    path = "~/" + "dossier/" * 30 + "facture_finale.pdf"
    summary = confirmation.summarize("localFiles", {"operation": "delete", "path": path})
    assert summary.endswith("facture_finale.pdf")
    assert "…" in summary and not summary.split("sur ", 1)[1].startswith("~")


def test_long_path_key_keeps_its_end_for_other_tools():
    path = "C:/" + "x" * 200 + "/secret.docx"
    summary = confirmation.summarize("someTool", {"path": path})
    assert "secret.docx" in summary


def test_long_non_path_value_keeps_its_start():
    summary = confirmation.summarize("someTool", {"query": "début" + "z" * 200})
    assert "début" in summary and "…" in summary


def test_omitted_arguments_are_reported():
    args = {f"k{i}": f"v{i}" for i in range(8)}
    summary = confirmation.summarize("someTool", args)
    assert "k0=v0" in summary and "k4=v4" in summary and "k5" not in summary
    assert "+3 arguments non affichés" in summary


def test_single_omitted_argument_uses_singular():
    args = {f"k{i}": "v" for i in range(6)}
    assert "+1 argument non affiché" in confirmation.summarize("someTool", args)
    assert "arguments" not in confirmation.summarize("someTool", args).split("+1", 1)[1]


def test_no_notice_when_everything_is_shown():
    assert "non affich" not in confirmation.summarize("someTool", {"a": 1, "b": 2})


def test_local_files_extra_arguments_are_reported():
    summary = confirmation.summarize("localFiles", {
        "operation": "write", "path": "~/a", "content": "x", "mode": "w", "force": True})
    assert "+2 arguments non affichés" in summary


def test_budget_drops_arguments_but_reports_them():
    args = {f"key{i}": "v" * 200 for i in range(5)}
    summary = confirmation.summarize("someTool", args)
    assert len(summary) <= ipc.MAX_SUMMARY_CHARS
    assert "non affich" in summary
    shown = summary.count("key")
    assert f"+{5 - shown} argument" in summary


def test_summary_is_always_bounded_so_the_notice_survives_the_frame():
    args = {"k" * 500 + str(i): "v" * 5000 for i in range(50)}
    summary = confirmation.summarize("t" * 5000, args)
    assert len(summary) <= ipc.MAX_SUMMARY_CHARS
    request = confirmation.ConfirmationRequest(
        "abc123", "t", "", Risk.EXTERNAL, summary, 60.0)
    parsed = ipc.parse_request_frame(ipc.request_frame(request))
    assert parsed is not None and parsed["summary"] == summary


def test_file_content_is_still_never_shown():
    summary = confirmation.summarize("localFiles", {
        "operation": "write", "path": "~/a.txt", "content": "secret"})
    assert "secret" not in summary and "6 caractères" in summary


def test_non_dict_arguments_do_not_crash():
    assert confirmation.summarize("someTool", None) == "someTool"
    assert confirmation.summarize("localFiles", ["delete"]) == "localFiles"
    assert confirmation.summarize("someTool", {}) == "someTool"
