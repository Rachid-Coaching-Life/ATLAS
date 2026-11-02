"""Desktop confirmation frames must never appear in general activity logs."""

import pytest

from desktop_app.app import _should_emit_as_log, LogSignals
from jarvis.tools.confirmation_ipc import (
    REQUEST_PREFIX, CANCEL_PREFIX, REPLY_PREFIX,
)


@pytest.mark.parametrize("prefix", [REQUEST_PREFIX, CANCEL_PREFIX, REPLY_PREFIX])
def test_confirmation_frames_are_not_general_logs(prefix):
    assert _should_emit_as_log(prefix + '{"request_id":"abc"}\n') is False


def test_regular_activity_remains_visible():
    assert _should_emit_as_log("ATLAS démarré\n") is True


def test_embedded_output_does_not_emit_confirmation_frames():
    signals = LogSignals()
    seen = []
    signals.new_log.connect(seen.append)
    signals.dispatch_output(REQUEST_PREFIX + '{"request_id":"abc"}\n')
    signals.dispatch_output(CANCEL_PREFIX + '{"request_id":"abc"}\n')
    signals.dispatch_output(REPLY_PREFIX + '{"request_id":"abc"}\n')
    assert seen == []
    signals.dispatch_output("Activité normale\n")
    assert seen == ["Activité normale\n"]
