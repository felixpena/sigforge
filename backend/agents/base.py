"""
Base agent class — wraps Anthropic Claude API calls with
structured JSON output parsing, retry logic, and logging.
"""
import asyncio
import json
import os
import re
from typing import Optional, Type, TypeVar
from datetime import datetime

import anthropic
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
import redis_client as rc
from models import AgentLogEntry

T = TypeVar("T", bound=BaseModel)

_client: Optional[anthropic.Anthropic] = None


def get_anthropic_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        key_preview = (api_key[:8] + "...") if api_key else "NOT SET"
        print(f"[ANTHROPIC] Initializing client — API key: {key_preview}")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


class BaseAgent:
    name: str = "BASE"
    system_prompt: str = ""
    output_model: Type[BaseModel] = BaseModel

    async def _log(self, level: str, message: str, data: Optional[dict] = None):
        entry = AgentLogEntry(
            agent=self.name,
            level=level,
            message=message,
            data=data,
        )
        await rc.log_agent_event(entry)
        return entry

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def _call_claude(
        self,
        user_message: str,
        tools: Optional[list] = None,
        max_tokens: int = 4096,
    ) -> str:
        """Call Claude via the synchronous client in a thread pool."""
        client = get_anthropic_client()
        kwargs = {
            "model": settings.claude_model,
            "max_tokens": max_tokens,
            "system": self.system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }
        if tools:
            kwargs["tools"] = tools

        response = await asyncio.to_thread(client.messages.create, **kwargs)

        # Extract text from response
        for block in response.content:
            if hasattr(block, "text"):
                return block.text

        return ""

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from Claude response, handling markdown code blocks."""
        # Try direct parse first
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from code block
        patterns = [
            r"```json\s*([\s\S]*?)```",
            r"```\s*([\s\S]*?)```",
            r"\{[\s\S]*\}",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                candidate = match.group(1) if "```" in pattern else match.group(0)
                try:
                    return json.loads(candidate.strip())
                except json.JSONDecodeError:
                    continue

        raise ValueError(f"Could not extract JSON from response: {text[:200]}")

    async def _parse_output(self, text: str) -> BaseModel:
        data = self._extract_json(text)
        return self.output_model.model_validate(data)
