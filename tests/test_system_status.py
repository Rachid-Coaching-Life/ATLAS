"""Read-only system diagnostics and direct ATLAS task execution."""

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

_GIB = 1024 ** 3


def _set_sample_counters(monkeypatch):
    from jarvis.tools.builtin import system_status

    monkeypatch.setattr(
        system_status.psutil, "cpu_percent",
        lambda interval: 17.5 if interval == 0.1 else 999,
    )
    monkeypatch.setattr(
        system_status.psutil, "virtual_memory",
        lambda: SimpleNamespace(
            total=16 * _GIB, used=8 * _GIB, percent=50.0,
        ),
    )
    monkeypatch.setattr(
        system_status.psutil, "disk_usage",
        lambda path: SimpleNamespace(
            total=500 * _GIB, free=125 * _GIB,
        ),
    )


def test_system_status_is_measured_and_read_only(monkeypatch):
    from jarvis.tools.builtin.system_status import SystemStatusTool
    from jarvis.tools.registry import BUILTIN_TOOLS, generate_tools_json_schema

    _set_sample_counters(monkeypatch)
    tool = BUILTIN_TOOLS["systemStatus"]
    assert isinstance(tool, SystemStatusTool)
    assert any(
        row["function"]["name"] == "systemStatus"
        for row in generate_tools_json_schema(["systemStatus"])
    )
    result = tool.run({}, None)
    assert result.success
    assert "CPU utilisé : 17.5 %" in result.reply_text
    assert "RAM utilisée : 8.0 / 16.0 Gio (50.0 %)" in result.reply_text
    assert "125.0 / 500.0 Gio" in result.reply_text
    assert "ne mesure ni GPU ni températures" in result.reply_text
    assert tool.run({"force": True}, None).success is False


def test_direct_status_task_bypasses_model_and_reports_real_result(monkeypatch):
    from jarvis import tasks

    _set_sample_counters(monkeypatch)

    def no_model(*args, **kwargs):
        raise AssertionError("Le diagnostic direct ne doit pas appeler le modèle")

    monkeypatch.setattr(tasks, "run_reply_engine", no_model)
    events = []
    manager = tasks.TaskManager(
        db=object(), cfg=object(), dialogue_memory=None,
        event_callback=events.append,
    )
    try:
        identity = manager.submit("Diagnostic système")
        manager.wait_for_idle(timeout=5)
        item = manager.get(identity)
        assert item.status == tasks.TaskStatus.COMPLETED
        assert "CPU utilisé : 17.5 %" in item.result
        assert [event["status"] for event in events] == [
            "queued", "running", "completed"
        ]
    finally:
        manager.shutdown()


def test_status_failure_is_failed_not_completed(monkeypatch):
    from jarvis import tasks
    from jarvis.tools.builtin import system_status

    def broken_measurement(interval):
        raise PermissionError("Counter inaccessible")

    monkeypatch.setattr(system_status.psutil, "cpu_percent", broken_measurement)
    manager = tasks.TaskManager(
        db=object(), cfg=object(), dialogue_memory=None,
    )
    try:
        identity = manager.submit("État du système")
        manager.wait_for_idle(timeout=5)
        item = manager.get(identity)
        assert item.status == tasks.TaskStatus.FAILED
        assert "Impossible de relever" in item.error
        assert item.result is None
    finally:
        manager.shutdown()


@pytest.mark.parametrize(
    ("prompt", "direct"),
    [
        ("Diagnostic système", True),
        ("état du système", True),
        ("Vérifie l'état de mon ordinateur.", True),
        ("diagnostic du GPU", False),
        ("Vérifie mes fichiers et efface les anciens", False),
        ("Vérifie l'état de mon ordinateur et supprime les erreurs", False),
        ("Explique comment faire un diagnostic système", False),
    ],
)
def test_direct_command_only_matches_read_only_intents(prompt, direct):
    from jarvis.tasks import _is_direct_system_status_task

    assert _is_direct_system_status_task(prompt) is direct
