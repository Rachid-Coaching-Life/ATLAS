"""Explicit social conversation stays responsive without tool planning."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from jarvis.reply import engine

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("no_network")]


@pytest.mark.parametrize(("text", "expected"), [
    ("Atlas, de quoi veux-tu qu'on parle ?", True),
    ("De quoi veux-tu qu'on dise ?", True),
    ("Comment vas-tu ?", True),
    ("Bonjour", True),
    ("Salut ATLAS", False),
    ("On peut discuter ensemble ?", True),
    ("Je veux discuter avec toi.", True),
    ("Ouvre mon dossier", False),
    ("Comment ouvrir mon dossier ?", False),
    ("De quoi parlons-nous dans le document ?", False),
    ("Peux-tu ouvrir Spotify et discuter ?", False),
    ("Donne-moi la météo", False),
    ("Réserve un restaurant", False),
    ("Parle de mes rendez-vous", False),
    ("De quoi veux-tu qu'on parle et envoie un mail ?", False),
])
def test_only_safe_social_phrases_are_direct_chat(text, expected):
    assert engine._is_simple_conversation_query(text) is expected


def test_simple_chat_skips_preparations_and_caps_generation(capsys):
    memory = MagicMock()
    voice = SimpleNamespace(enabled=True, speak=MagicMock())
    with patch.object(engine, "chat_with_messages", return_value={
        "message": {"role": "assistant", "content": "Parlons de ce qui t'intéresse !"}
    }) as model, \
         patch.object(engine, "select_tools", side_effect=AssertionError("router")), \
         patch.object(engine, "plan_query", side_effect=AssertionError("planner")), \
         patch.object(engine, "extract_search_params_for_memory", side_effect=AssertionError("memory")):
        result = engine.run_reply_engine(
            db=object(), cfg=SimpleNamespace(llm_chat_model="qwen3.5:0.8b"),
            tts=voice, text="Je veux discuter avec toi.", dialogue_memory=memory,
        )

    assert result == "Parlons de ce qui t'intéresse !"
    model.assert_called_once()
    kwargs = model.call_args.kwargs
    assert kwargs["timeout_sec"] == 18.0
    assert kwargs["extra_options"]["max_tokens"] == 80
    assert kwargs["extra_options"]["num_ctx"] == 2048
    assert kwargs["tools"] is None
    assert kwargs["thinking"] is False
    assert model.call_args.args[1][0]["role"] == "system"
    voice.speak.assert_called_once_with(result)
    assert memory.add_message.call_count == 2
    assert "🤖 ATLAS" in capsys.readouterr().out


def test_simple_chat_backend_timeout_has_prompt_fallback():
    voice = SimpleNamespace(enabled=False, speak=MagicMock())
    with patch.object(engine, "chat_with_messages", return_value=None):
        result = engine.run_reply_engine(
            db=object(), cfg=SimpleNamespace(), tts=voice,
            text="Bonjour", dialogue_memory=None,
        )
    assert result.startswith("Je suis là")
    voice.speak.assert_not_called()


def test_simple_chat_cancellation_has_no_voice_or_memory():
    voice = SimpleNamespace(enabled=True, speak=MagicMock())
    memory = MagicMock()
    state = {"cancel": False}

    def cancel_during_chat(*args, **kwargs):
        state["cancel"] = True
        return {"message": {"content": "Réponse tardive"}}

    with patch.object(engine, "chat_with_messages", side_effect=cancel_during_chat):
        result = engine.run_reply_engine(
            db=object(), cfg=SimpleNamespace(), tts=voice,
            text="Bonjour", dialogue_memory=memory,
            cancel_event=SimpleNamespace(is_set=lambda: state["cancel"]),
        )
    assert result is None
    voice.speak.assert_not_called()
    memory.add_message.assert_not_called()


def test_invitation_to_talk_answers_immediately_without_llm_or_tools():
    voice = SimpleNamespace(enabled=True, speak=MagicMock())
    with patch.object(engine, "chat_with_messages", side_effect=AssertionError("model")), \
         patch.object(engine, "select_tools", side_effect=AssertionError("router")), \
         patch.object(engine, "plan_query", side_effect=AssertionError("planner")):
        result = engine.run_reply_engine(
            db=object(), cfg=SimpleNamespace(), tts=voice,
            text="Atlas, de quoi veux-tu qu'on dise ?", dialogue_memory=None,
        )
    assert "De quoi as-tu envie de parler" in result
    voice.speak.assert_called_once_with(result)
