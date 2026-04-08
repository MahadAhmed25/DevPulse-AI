import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_service import LLMService


def test_llm_service_parses_valid_json() -> None:
    """LLMService must parse a clean JSON response from the model."""
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text=json.dumps({
                "summary": "Looks good overall.",
                "comments": [
                    {
                        "path": "app/main.py",
                        "line": 10,
                        "severity": "bug",
                        "body": "Missing null check",
                    }
                ],
            })
        )
    ]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50

    with patch("app.services.llm_service.anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create.return_value = mock_response
        service = LLMService()
        result, tokens = service.review_pull_request(diff="some diff", rag_context="some context")

    assert result["summary"] == "Looks good overall."
    assert len(result["comments"]) == 1
    assert result["comments"][0]["severity"] == "bug"
    assert tokens == 150


def test_llm_service_extracts_json_from_prose() -> None:
    """LLMService must handle model responses that wrap JSON in prose."""
    wrapped = 'Here is the review:\n{"summary": "ok", "comments": []}\nEnd.'
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=wrapped)]
    mock_response.usage.input_tokens = 50
    mock_response.usage.output_tokens = 20

    with patch("app.services.llm_service.anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create.return_value = mock_response
        service = LLMService()
        result, tokens = service.review_pull_request(diff="diff", rag_context="ctx")

    assert result["summary"] == "ok"
    assert result["comments"] == []
