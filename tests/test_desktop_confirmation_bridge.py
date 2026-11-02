"""Regression tests for the desktop confirmation bridge (Qt offscreen)."""
import io
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

from desktop_app.app import ATLASSystemTray, LogSignals
from jarvis.tools.confirmation import ConfirmationRequest, Risk
from jarvis.tools.confirmation_ipc import request_frame, cancel_frame, reply_line


class FakeProcess:
    def __init__(self):
        self.stdin = io.StringIO()
    def poll(self):
        return None


def _app():
    return QApplication.instance() or QApplication([])


def _tray(process):
    tray = ATLASSystemTray.__new__(ATLASSystemTray)
    tray.daemon_process = process
    tray.daemon_thread = None
    tray._confirmation_pending = {}
    return tray


def _frame(request_id="request_1", timeout=60.0):
    return request_frame(ConfirmationRequest(
        request_id=request_id, tool="localFiles", operation="write",
        risk=Risk.WRITE, summary="Écrire un fichier fictif", timeout_sec=timeout,
    ))


def test_subprocess_confirmation_approval_and_denial():
    app = _app()
    process = FakeProcess()
    tray = _tray(process)
    tray._on_confirmation_frame(_frame("yes"), process)
    dialog, _ = tray._confirmation_pending["yes"]
    next(button for button in dialog.buttons() if button.text() == "Autoriser").click()
    app.processEvents()
    assert process.stdin.getvalue() == reply_line("yes", True) + "\n"
    tray._on_confirmation_frame(_frame("no"), process)
    dialog, _ = tray._confirmation_pending["no"]
    next(button for button in dialog.buttons() if button.text() == "Refuser").click()
    app.processEvents()
    assert process.stdin.getvalue().endswith(reply_line("no", False) + "\n")


def test_unknown_cancel_duplicate_and_stale_daemon():
    app = _app()
    process = FakeProcess()
    tray = _tray(process)
    tray._on_confirmation_frame(_frame("one"), FakeProcess())
    assert not tray._confirmation_pending
    tray._on_confirmation_frame(_frame("one"), process)
    first = tray._confirmation_pending["one"][0]
    tray._on_confirmation_frame(_frame("one"), process)
    assert tray._confirmation_pending["one"][0] is first
    tray._on_confirmation_frame(cancel_frame(ConfirmationRequest(
        request_id="unknown", tool="localFiles", operation="write",
        risk=Risk.WRITE, summary="x", timeout_sec=60.0,
    )), process)
    assert "one" in tray._confirmation_pending
    tray._close_confirmation_dialogs()
    app.processEvents()
    assert not tray._confirmation_pending
    assert process.stdin.getvalue() == ""


def test_embedded_confirmation_frames_use_private_signal():
    _app()
    signals = LogSignals()
    seen, logs = [], []
    signals.confirmation_frame.connect(lambda line, source: seen.append((line, source)))
    signals.new_log.connect(logs.append)
    signals.dispatch_output(_frame("embedded") + "\n")
    assert len(seen) == 1
    assert seen[0][1] is None
    assert logs == []
