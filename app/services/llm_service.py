import json
import time

import anthropic
import structlog

from app.config import get_settings
from app.schemas.review import ReviewComment, ReviewResult

logger = structlog.get_logger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are an expert code reviewer. You analyze pull request diffs and provide
structured, actionable feedback. You are given:
1. The PR diff showing what changed
2. Relevant context from the existing codebase retrieved via semantic search

Your review must be thorough but concise. Focus on:
- Bugs and logic errors (highest priority)
- Security vulnerabilities (SQL injection, auth bypass, secrets in code, etc.)
- Performance issues (N+1 queries, unnecessary loops, memory leaks)
- Code quality (naming, duplication, missing error handling)
- Missing tests for changed logic

Respond ONLY with valid JSON matching this exact schema:
{
  "summary": "2-3 sentence overall assessment",
  "verdict": "approve" | "request_changes" | "comment",
  "comments": [
    {
      "file_path": "path/to/file.py",
      "line_number": 42,
      "severity": "bug" | "security" | "performance" | "suggestion" | "style",
      "title": "Short title",
      "body": "Detailed explanation with suggested fix"
    }
  ],
  "bugs_found": <integer>,
  "security_issues": <integer>,
  "suggestions": <integer>
}

If the diff is clean, return empty comments array and verdict "approve".
Never make up file paths or line numbers — only reference what is in the diff."""


class LLMService:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def generate_code_review(
        self,
        diff: str,
        context_chunks: list[str],
        pr_title: str,
        use_sonnet: bool = False,
    ) -> ReviewResult:
        """Call Claude and return a structured ReviewResult."""
        model = SONNET_MODEL if use_sonnet else HAIKU_MODEL
        joined_chunks = "\n\n---\n\n".join(context_chunks)
        user_msg = (
            f"PR Title: {pr_title}\n\n"
            f"CODEBASE CONTEXT:\n{joined_chunks}\n\n"
            f"PR DIFF:\n{diff}"
        )

        start = time.perf_counter()
        messages: list[dict[str, str]] = [{"role": "user", "content": user_msg}]

        response = await self._client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        tokens_used = response.usage.input_tokens + response.usage.output_tokens
        raw = response.content[0].text.strip()  # type: ignore[union-attr]

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Retry once with an explicit JSON-only instruction
            retry_messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "Respond only with valid JSON, no preamble."},
            ]
            response2 = await self._client.messages.create(
                model=model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=retry_messages,
            )
            tokens_used += response2.usage.input_tokens + response2.usage.output_tokens
            raw2 = response2.content[0].text.strip()  # type: ignore[union-attr]
            data = json.loads(raw2)

        processing_time_ms = int((time.perf_counter() - start) * 1000)

        result = ReviewResult(
            summary=data.get("summary", ""),
            verdict=data.get("verdict", "comment"),
            comments=[ReviewComment(**c) for c in data.get("comments", [])],
            bugs_found=int(data.get("bugs_found", 0)),
            security_issues=int(data.get("security_issues", 0)),
            suggestions=int(data.get("suggestions", 0)),
            model_used=model,
            tokens_used=tokens_used,
            processing_time_ms=processing_time_ms,
        )

        logger.info(
            "LLM review complete",
            model=model,
            tokens_used=tokens_used,
            processing_time_ms=processing_time_ms,
            comments=len(result.comments),
            verdict=result.verdict,
        )
        return result
