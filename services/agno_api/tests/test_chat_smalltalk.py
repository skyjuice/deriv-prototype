from __future__ import annotations

import asyncio

from app.ai import answer_data_question


def test_chat_handles_greeting_without_not_found() -> None:
    context = {"summary": {"runs_total": 12, "open_exceptions": 2}}
    result = asyncio.run(answer_data_question("hello", context))
    assert result["source"] == "system"
    assert "Not found in current database snapshot." not in result["answer"]
    assert "Current snapshot" in result["answer"]


def test_chat_handles_help_prompt() -> None:
    context = {"summary": {"runs_total": 5, "open_exceptions": 0}}
    result = asyncio.run(answer_data_question("help", context))
    assert result["source"] == "system"
    assert "Try:" in result["answer"]
