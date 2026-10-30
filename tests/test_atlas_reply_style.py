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
            "votre assistant. Il est 16 h.",
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


def test_startup_presentation_is_queued_once_when_daemon_calls_helper():
    from jarvis.daemon import _announce_atlas_startup, _ATLAS_STARTUP_GREETING

    class FakeTTS:
        enabled = True

        def __init__(self):
            self.queued = []

        def speak(self, text):
            self.queued.append(text)

    tts = FakeTTS()
    assert _announce_atlas_startup(tts) is True
    assert tts.queued == [_ATLAS_STARTUP_GREETING]
    assert _ATLAS_STARTUP_GREETING.startswith("Bonjour, je suis ATLAS.")
    tts.enabled = False
    assert _announce_atlas_startup(tts) is False
    assert len(tts.queued) == 1
    assert _announce_atlas_startup(None) is False
