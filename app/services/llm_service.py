import json
from typing import Any

import anthropic
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

REVIEW_SYSTEM_PROMPT = """You are DevPulse AI, an expert code reviewer.
You analyse GitHub pull request diffs alongside relevant context from the repository.
You return structured, actionable feedback only — no filler, no praise.

Respond ONLY with a valid JSON object matching this schema:
{
  "summary": "<1-3 sentence overall assessment>",
  "comments": [
    {
      "path": "<file path>",
      "line": <line number as integer>,
      "severity": "<bug|suggestion|security|style>",
      "body": "<concise actionable comment>"
    }
  ]
}
"""


class LLMService:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def review_pull_request(
        self,
        diff: str,
        rag_context: str,
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 4096,
    ) -> tuple[dict[str, Any], int]:
        """Run the PR review. Returns (structured_review_dict, tokens_used)."""
        user_message = f"""<rag_context>
{rag_context}
</rag_context>

<pull_request_diff>
{diff}
</pull_request_diff>

Review the pull request diff. Use the RAG context to understand the codebase conventions and
existing patterns. Return ONLY the JSON object described in the system prompt."""

        message = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=REVIEW_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        tokens_used = message.usage.input_tokens + message.usage.output_tokens
        raw_content = message.content[0].text.strip()

        try:
            structured = json.loads(raw_content)
        except json.JSONDecodeError:
            # Attempt to extract JSON from the response if the model added prose
            start = raw_content.find("{")
            end = raw_content.rfind("}") + 1
            structured = json.loads(raw_content[start:end])

        logger.info(
            "LLM review complete",
            model=model,
            tokens_used=tokens_used,
            comments_count=len(structured.get("comments", [])),
        )
        return structured, tokens_used
