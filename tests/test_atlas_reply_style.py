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
            "Bonjour. Je suis ATLAS.",
        ),
    ],
)
def test_repeated_introduction_guard_is_narrow(query, reply, expected):
    from jarvis.reply.engine import _remove_unrequested_atlas_introduction

    assert _remove_unrequested_atlas_introduction(reply, query) == expected
