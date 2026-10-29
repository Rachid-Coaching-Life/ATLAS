"""ATLAS direct self-introduction is fast, grounded, and cannot execute tools."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from jarvis.reply import engine


@pytest.mark.unit
@pytest.mark.parametrize(("query", "expected"), [
    ("Présente-toi en français.", True),
    ("Atlas, présente-toi en français.", True),
    ("Atlasse, présente-toi en français.", True),
    ("Tu peux te présenter en français ?", True),
    ("Peux-tu te présenter ?", True),
    ("Qui es-tu ?", True),
    ("Atlas, qui es-tu ?", True),
    ("Présente-toi et ouvre mon dossier", False),
    ("Atlas, présente-toi puis envoie un message", False),
    ("Peux-tu te présenter et donner la météo ?", False),
    ("Que sais-tu de moi ?", False),
    ("Ouvre mon dossier", False),
    ("Présente notre projet en français", False),
    ("Parle-moi d'un atlas géographique", False),
])
def test_only_unambiguous_self_intro_uses_fast_path(query, expected):
    assert engine._is_atlas_self_introduction_request(query) is expected


@pytest.mark.unit
def test_self_intro_needs_no_llm_or_tools_and_preserves_voice_and_memory(capsys):
    tts = SimpleNamespace(enabled=True, speak=MagicMock())
    memory = MagicMock()

    with patch.object(engine, "select_tools", side_effect=AssertionError("tool router called")), \
         patch.object(engine, "plan_query", side_effect=AssertionError("planner called")), \
         patch.object(engine, "chat_with_messages", side_effect=AssertionError("LLM called")):
        reply = engine.run_reply_engine(
            db=object(), cfg=SimpleNamespace(voice_debug=False), tts=tts,
            text="Présente-toi en français.", dialogue_memory=memory,
            language="fr",
        )

    assert reply.startswith("Je suis ATLAS")
    assert "français" in reply
    tts.speak.assert_called_once_with(reply)
    assert memory.add_message.call_args_list == [
        (("user", "Présente-toi en français."),),
        (("assistant", reply),),
    ]
    output = capsys.readouterr().out
    assert "🤖 ATLAS" in output
    assert "🤖 Jarvis" not in output


@pytest.mark.unit
def test_self_intro_quiet_mode_does_not_print_or_speak(capsys):
    tts = SimpleNamespace(enabled=False, speak=MagicMock())
    memory = MagicMock()
    reply = engine.run_reply_engine(
        db=object(), cfg=SimpleNamespace(voice_debug=False), tts=tts,
        text="Atlas, qui es-tu ?", dialogue_memory=memory, quiet=True,
    )
    assert reply.startswith("Je suis ATLAS")
    assert "🤖 ATLAS" not in capsys.readouterr().out
    tts.speak.assert_not_called()


@pytest.mark.unit
def test_cancelled_self_intro_produces_no_output():
    tts = SimpleNamespace(enabled=True, speak=MagicMock())
    memory = MagicMock()
    cancel = SimpleNamespace(is_set=lambda: True)
    result = engine.run_reply_engine(
        db=object(), cfg=SimpleNamespace(voice_debug=False), tts=tts,
        text="Présente-toi", dialogue_memory=memory, cancel_event=cancel,
    )
    assert result is None
    tts.speak.assert_not_called()
    memory.add_message.assert_not_called()
