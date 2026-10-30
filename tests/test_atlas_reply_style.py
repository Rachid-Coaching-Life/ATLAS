"""ATLAS task-first reply rules: only strip unrequested stock introductions."""

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("query", "reply", "expected"),
    [
        (
            "Combien font deux et deux ?",
            "Bonjour. Je suis ATLAS. Deux et deux font quatre.",
            "Deux et deux font quatre.",
        ),
        (
            "Quelle est l'heure ?",
            "Je suis Atlas, votre assistant. Il est 16 h.",
            "Il est 16 h.",
        ),
        (
            "Lance cette tâche",
            "Le fichier a été créé après confirmation de l'outil.",
            "Le fichier a été créé après confirmation de l'outil.",
        ),
        (
            "Présente-toi",
            "Bonjour. Je suis ATLAS. Assistant personnel local.",
            "Bonjour. Je suis ATLAS. Assistant personnel local.",
        ),
        (
            "Bonjour Atlas, réponds",
            "Bonjour. Je suis ATLAS.",
            "Je n'ai pas de réponse fiable. Pouvez-vous préciser votre demande ?",
        ),
    ],
)
def test_repeated_introduction_guard_is_narrow(query, reply, expected):
    from jarvis.reply.engine import _remove_unrequested_atlas_introduction

    assert _remove_unrequested_atlas_introduction(reply, query) == expected


def test_startup_presentation_is_spoken_once_after_voice_ready():
    from jarvis.listening.listener import VoiceListener

    calls = []
    class FakeTTS:
        enabled = True

        def speak(self, text, terminal_callback=None):
            calls.append(text)
            if terminal_callback is not None:
                terminal_callback("completed")

    class FakeListener:
        _should_stop = False
        tts = FakeTTS()
        capture_paused = False

        def set_capture_paused(self, reason, paused):
            assert reason == "startup_greeting"
            calls.append(("pause", paused))

    listener = FakeListener()
    VoiceListener._announce_voice_ready(listener)
    assert calls == [
        ("pause", True),
        "Bonjour, je suis ATLAS. Je suis prêt à exécuter vos tâches.",
        ("pause", False),
    ]
    listener.tts.enabled = False
    VoiceListener._announce_voice_ready(listener)
    assert len([call for call in calls if isinstance(call, str)]) == 1
