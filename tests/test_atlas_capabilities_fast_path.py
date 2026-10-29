"""Everyday ATLAS capability questions must not invoke expensive tool/memory inference."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from jarvis.reply import engine

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("no_network")]


@pytest.mark.parametrize(("utterance", "expected"), [
    ("Atlas, tu peux me dire ce que tu peux faire ?", True),
    ("Là, si tu peux me dire ce que tu peux faire.", True),
    ("Ce que tu peux faire ?", True),
    ("Quelles sont tes capacités ?", True),
    ("Quelles sont tes fonctions ?", True),
    ("À quoi sers-tu ?", True),
    ("Que sais-tu faire ?", True),
    ("Atlas, que sais-tu faire ?", True),
    ("Atlas, ouvre mon dossier", False),
    ("Tu peux me dire la météo ?", False),
    ("Que peux-tu faire pour réparer ce fichier ?", False),
    ("Quelles sont mes capacités ?", False),
    ("Quelles sont tes fonctions et ouvre mon dossier", False),
    ("Ce que tu peux faire avec mon calendrier", False),
    # Observed Whisper substitution of "ce que tu peux" by "si tu veux".
    ("Atlas, tu peux me dire si tu veux faire ?", True),
])
def test_capability_phrase_is_strict_and_not_an_execution_request(utterance, expected):
    assert engine._is_atlas_capabilities_request(utterance) is expected


def test_capabilities_reply_never_uses_unrelated_memory_or_llm(capsys):
    tts = SimpleNamespace(enabled=True, speak=MagicMock())
    memory = MagicMock()
    with patch.object(engine, "select_tools", side_effect=AssertionError("router invoked")), \
         patch.object(engine, "plan_query", side_effect=AssertionError("planner invoked")), \
         patch.object(engine, "extract_search_params_for_memory", side_effect=AssertionError("memory invoked")), \
         patch.object(engine, "chat_with_messages", side_effect=AssertionError("model invoked")):
        reply = engine.run_reply_engine(
            db=object(), cfg=SimpleNamespace(voice_debug=False), tts=tts,
            text="Atlas, tu peux me dire ce que tu peux faire ?", dialogue_memory=memory,
            language="fr",
        )

    assert "Je peux discuter" in reply
    assert "outils" in reply
    assert "réserv" not in reply
    tts.speak.assert_called_once_with(reply)
    assert memory.add_message.call_count == 2
    assert "🤖 ATLAS" in capsys.readouterr().out


def test_capability_reply_respects_cancellation():
    tts = SimpleNamespace(enabled=True, speak=MagicMock())
    memory = MagicMock()
    cancelled = SimpleNamespace(is_set=lambda: True)
    assert engine.run_reply_engine(
        db=object(), cfg=SimpleNamespace(), tts=tts,
        text="Quelles sont tes fonctions ?", dialogue_memory=memory,
        cancel_event=cancelled,
    ) is None
    tts.speak.assert_not_called()
    memory.add_message.assert_not_called()
