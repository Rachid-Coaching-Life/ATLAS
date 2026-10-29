"""Live French-language evaluation for the personal ATLAS reply path.

Requires a reachable locally configured LLM. The unit prompt contract is
covered independently by tests/test_system_prompt.py.
"""

import pytest

from conftest import requires_judge_llm
from helpers import judge_pass_fail
from jarvis.reply.engine import run_reply_engine


@pytest.mark.eval
@requires_judge_llm
@pytest.mark.parametrize("query", [
    "Pourquoi le ciel est-il bleu ? Réponds en une phrase.",
    "Why is the sky blue? Answer in one sentence.",
])
def test_atlas_replies_in_french_with_live_local_model(
    query, mock_config, eval_db, eval_dialogue_memory,
):
    """Replies remain in French for both French and foreign-language input."""
    reply = run_reply_engine(
        db=eval_db,
        cfg=mock_config,
        tts=None,
        text=query,
        dialogue_memory=eval_dialogue_memory,
    )
    assert reply and reply.strip(), "Expected a real model reply"
    verdict = judge_pass_fail(
        "The assistant's response is written in natural French. "
        "Preserved proper nouns, file paths, URLs, and quoted code are acceptable. "
        "An English-language or bilingual explanation does not satisfy this criterion.",
        reply,
    )
    assert verdict == "PASS", f"French-only language evaluation: {verdict}: {reply!r}"
