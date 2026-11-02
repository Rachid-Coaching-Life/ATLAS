"""MCP tools always need a human confirmation (their effects are unknown)."""
from types import SimpleNamespace

import pytest

from jarvis.tools import confirmation


@pytest.fixture(autouse=True)
def _reset_provider():
    confirmation.set_provider(None)
    yield
    confirmation.set_provider(None)


@pytest.mark.unit
def test_registry_mcp_tool_needs_confirmation(monkeypatch):
    registry = pytest.importorskip("jarvis.tools.registry")
    invoked = []

    class FakeClient:
        def __init__(self, config):
            pass

        def invoke_tool(self, **kwargs):
            invoked.append(kwargs)
            return {"text": "done", "isError": False}

    monkeypatch.setattr(registry, "MCPClient", FakeClient)
    cfg = SimpleNamespace(voice_debug=False, mcps={"srv": {}})

    def call():
        return registry.run_tool_with_retries(
            db=None, cfg=cfg, tool_name="srv__delete_everything",
            tool_args={"x": 1}, system_prompt="", original_prompt="",
            redacted_text="", max_retries=0,
        )

    assert call().success is False and invoked == []
    confirmation.set_provider(lambda request: False)
    assert call().success is False and invoked == []
    confirmation.set_provider(lambda request: True)
    assert call().success is True and len(invoked) == 1
